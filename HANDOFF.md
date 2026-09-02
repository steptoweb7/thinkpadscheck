# HANDOFF — OLX Business Laptop Alert Bot

> Document de continuitate intre sesiuni. Citeste asta primul lucru cand
> reiei lucrul la acest proiect. Actualizeaza-l pe masura ce avansezi.

**Ultima actualizare:** 2026-09-02, in timpul sesiunii de implementare
(intrerupt manual de user chiar inainte de review-ul final pe toata
ramura — vezi Capitolul 6, "Unde am ramas exact").

---

## Capitolul 1: Ce se construieste si de ce

User (media@germancardepot.com) vrea un bot care scaneaza OLX.ro pentru
laptop-uri **business-class** (ThinkPad / Latitude / EliteBook) la
preturi foarte bune ("super oferte", "pomeni"), si trimite alerta pe
email cand gaseste ceva bun. Ruleaza pe un mini PC HP cu Windows care e
deja pornit 24/7 (acelasi PC ruleaza Jellyfin).

Cerinte esentiale stabilite prin brainstorming (vezi Capitolul 2 pentru
tot procesul de intrebari/raspunsuri):

- Model: ThinkPad T480/T490/T14/X13/P14s/L14/X1, Dell Latitude, HP
  EliteBook/ProBook.
- RAM >= 16GB.
- CPU: Intel generatia 11+ (sau echivalent AMD Ryzen PRO 5000+).
- SSD obligatoriu (nu HDD).
- Nu defect / nu "pentru piese".
- Pret <= 1500 lei.
- Notificare: **email** (Gmail SMTP, cu app password).
- Frecventa scanare: **orar**.
- Deploy: mini PC HP Windows, Task Scheduler.
- Scor de "cat de buna e oferta": % sub un pret de referinta per model,
  tinut manual intr-un tabel in config (nu invatare automata din
  istoric — deliberat, YAGNI).

---

## Capitolul 2: Cum s-a ajuns la design (brainstorming)

Am folosit skill-ul `superpowers:brainstorming`, clasificat ca
**architectural** (proiect nou, fara cod existent in director).

Secventa de intrebari/decizii (rezumat, ordine cronologica):

1. Notificare → **Email** (nu Telegram/Discord).
2. Logica "super oferta" → **combinatie prag fix + comparatie cu
   media pietei**.
3. Frecventa scanare → **orar** (nu 15-30 min, nu zilnic).
4. Deployment → **mini PC HP Windows, 24/7** (nu cloud).
5. Prag pret initial → **sub 1000 lei** (link de filtru OLX generat
   pentru asta — vezi mai jos).
6. Arhitectura propusa (scraper → parser → SQLite → scorer → email,
   orar) → **aprobata**, dar cu adaugarea filtrului de clasa business
   (ThinkPad T480/T490/P14s/X13/T14 etc, minim 16GB RAM, minim Intel
   gen 11, SSD obligatoriu).
7. Branduri business → **ThinkPad + Dell Latitude + HP
   EliteBook/ProBook** (nu doar Lenovo).
8. **Contradictie descoperita**: laptop-uri business cu specificatiile
   cerute rar apar sub 1000 lei. Am intrebat explicit → user a ales
   **sub 1500 lei** pentru clasa business.
9. Design simplificat propus (fara scor de valoare, doar reguli fixe)
   → user a cerut **inapoi scorul**, plus **exclude anunturi
   defecte/pe piese** (uitase sa mentioneze asta).
10. Baza pentru scor → **tabel manual cu preturi de referinta per
    model** (nu medie invatata automat din date scanate — cel putin
    pentru inceput).

Toate aceste decizii sunt inregistrate detaliat, cu motivatie, in
spec-ul scris (Capitolul 3).

### Descoperire tehnica importanta (facuta live, cu Browser tool)

Am incercat sa scrap-uiesc pagina OLX cu `curl` simplu si am observat
ca **doar 3 anunturi "promovate" apar ca elemente DOM reale** in HTML-ul
static — restul sunt hidratate client-side prin JavaScript. Asta ar fi
facut inutila orice abordare cu BeautifulSoup / selectori CSS.

Investigand mai departe (`grep` dupa `window.__`), am gasit
`window.__PRERENDERED_STATE__` — un blob JSON (dublu-encodat: string
JSON continand alt JSON) care contine **toate anunturile** de pe
pagina, cu date structurate mult mai bune decat orice am fi extras din
HTML randat:

- `id`, `title`, `description` (text complet, nu doar titlu), `url`,
  `createdTime`, `location.pathName`, `price.regularPrice.value`.
- `params[]`: array de filtre structurate alese de vanzator —
  `state` (Nou/Utilizat), `tip_stocare` (SSD/HDD/HDD+SSD),
  `capacitate_memorie_ram` (bucket-uri: `< 4 GB`, `4 - 6 GB`,
  `6 - 8 GB`, `8 - 12 GB`, `12 - 16 GB`, `> 16 GB`),
  `producator_procesor` (Intel/AMD/Apple), `tip_placa_video`
  (Integrata/Dedicata), `diagonala`.

**Nu exista camp structurat pentru generatia CPU** — asta ramane strict
regex pe `title + description`.

Aceasta descoperire a schimbat complet abordarea de scraping: un simplu
`requests.get()` + extractie regex a blob-ului JSON, fara Selenium,
fara JS execution, fara BeautifulSoup.

---

## Capitolul 3: Documentul de specificatii (spec)

**Fisier:** [`docs/superpowers/specs/2026-09-02-olx-business-laptop-alert-bot-design.md`](docs/superpowers/specs/2026-09-02-olx-business-laptop-alert-bot-design.md)

Continut principal:

- **Scope**: doar OLX laptopuri (nu multi-site), scriptul e headless
  (fara UI), nu invata preturi automat (v1), nu descarca pagina de
  detaliu a anuntului (doar pagina de cautare e suficienta).
- **Link de filtru referinta** (folosit ca `filter_url` in config):
  ```
  https://www.olx.ro/electronice-si-electrocasnice/laptop-calculator-gaming/laptopuri/?search%5Bfilter_float_price%3Ato%5D=1500&search%5Border%5D=created_at%3Adesc
  ```
  (pret <= 1500 lei, sortat dupa cele mai noi anunturi).
- **Sursa de date**: sectiunea "Data source" din spec documenteaza
  descoperirea `window.__PRERENDERED_STATE__` de mai sus, in detaliu.
- **Arhitectura**: `scraper.py` → `parser.py` → `filter.py` → `scorer.py`
  → `db.sqlite` (dedup) → `notifier.py`, rulat orar de Windows Task
  Scheduler.
- **6 reguli hard de filtrare** (toate trebuie sa treaca, AND):
  1. Nu defect/pentru piese (keyword matching pe text normalizat).
  2. Model business-class (regex pe familii de modele).
  3. RAM >= 16GB (din bucket-ul `capacitate_memorie_ram`, cu fallback
     regex pentru bucket-ul ambiguu `"12 - 16 GB"`).
  4. CPU generatia 11-13 Intel sau Ryzen 5-9 PRO 5000+ (regex, fara
     camp structurat disponibil).
  5. Storage SSD (`tip_stocare` == `"SSD"` sau `"HDD+SSD"`).
  6. Pret <= 1500 lei.
- **Scoring**: `% sub referinta = (pret_referinta - pret_anunt) /
  pret_referinta * 100`, cu tabel manual `reference_prices` in config.
  Daca modelul nu are pret de referinta in tabel, anuntul tot se
  trimite pe email, dar cu mesaj "scor indisponibil".
- **Deduplicare**: SQLite, tabel `seen_listings`, cheie primara `id`.
- **Notificare**: email prin Gmail SMTP (STARTTLS, port 587, app
  password).
- **Gestionare erori**: esec de scraping → logat in `bot.log`, NU
  trimite email (evita spam la hiccup-uri trecatoare); dupa **3 esecuri
  consecutive**, trimite UN singur email "bot-ul e oprit".
- **Riscuri documentate explicit** (asumate deliberat, nu bug-uri
  uitate): parsare bazata pe text liber pentru CPU poate rata fraze
  neobisnuite; bucket-ul RAM ambiguu cere mentiune explicita "16GB" in
  text; `window.__PRERENDERED_STATE__` e detaliu intern de
  implementare OLX si se poate schimba; tabelul de preturi de referinta
  are nevoie de intretinere manuala periodica.

---

## Capitolul 4: Planul de implementare

**Fisier:** [`docs/superpowers/plans/2026-09-02-olx-business-laptop-alert-bot.md`](docs/superpowers/plans/2026-09-02-olx-business-laptop-alert-bot.md)

8 task-uri, fiecare cu cod complet specificat (TDD: test intai, apoi
implementare minima), fisiere exacte, si mesaj de commit exact:

| # | Task | Fisiere principale | Produce |
|---|------|---------------------|---------|
| 1 | Scaffolding + config | `requirements.txt`, `.gitignore`, `config.example.yaml`, `olx_bot/config.py` | `load_config(path) -> dict` |
| 2 | Parser | `olx_bot/parser.py` | `extract_prerendered_state(html) -> dict`, `parse_listings(html) -> list[dict]` |
| 3 | Filtre hard | `olx_bot/filters.py` | `passes_hard_filters(listing, config) -> bool` |
| 4 | Scorer | `olx_bot/scorer.py` | `compute_score(title, description, price, reference_prices) -> {"model","score_pct"}` |
| 5 | DB dedup | `olx_bot/db.py` | `init_db`, `is_seen`, `mark_seen` |
| 6 | Notifier | `olx_bot/notifier.py` | `build_email`, `send_email` (Gmail SMTP) |
| 7 | Scraper HTTP | `olx_bot/scraper.py` | `fetch_html(url, timeout=15) -> str` |
| 8 | Main + deploy | `olx_bot/main.py`, `run.bat`, `README.md` | `run(config_path="config.yaml") -> None` |

**Global Constraints** din plan (valori exacte, copiate din spec):
prag pret 1500 lei, RAM>=16GB, CPU gen 11-13 Intel/Ryzen PRO 5000+,
SSD obligatoriu, lista de modele business, cuvinte cheie excluse,
text matching normalizat (lowercase + fara diacritice), `config.yaml`
niciodata commit-uit.

**Self-review-ul planului** (facut inainte de aprobare): am verificat
coverage-ul complet al spec-ului, am cautat placeholder-uri (niciunul
gasit), si am verificat consistenta tipurilor/semnaturilor intre
task-uri (toate corecte).

---

## Capitolul 5: Setup Git si worktree

1. **Repo git initializat local** (nu exista inainte): `git init`,
   apoi identitate locala setata explicit (nu global) la cererea
   user-ului:
   - `user.email = subscriptii123@gmail.com`
   - `user.name = steptoweb7`
2. **Remote GitHub**: `origin` → `https://github.com/steptoweb7/thinkpadscheck.git`
   (repo dat de user).
3. **Commit-uri pe `master`** (in ordine):
   - `16c50ba` — spec initial (design de laptop business + email +
     scor).
   - `1575efa` — actualizare spec cu descoperirea
     `window.__PRERENDERED_STATE__` + planul de implementare complet.
   - `4c0def1` — `.gitignore` cu `.worktrees/` (pregatire pentru
     worktree-ul de implementare — vezi mai jos).
4. **Push facut deja** catre `origin/master` (user a confirmat explicit
   "fa un push rapid acum").
5. **Worktree de implementare**: `EnterWorktree` (tool nativ) a esuat
   cu eroare ciudata ("not in a git repository") — probabil o problema
   de mapare de cale din cauza spatiilor din numele directorului
   (`AAntigravity`, `OLX Scraper`). Am facut fallback manual la
   `git worktree add`:
   ```
   .worktrees/olx-bot-impl/   (branch: olx-bot-impl, pornit din master la 4c0def1)
   ```
   **Toata implementarea (Task-urile 1-8) s-a facut in acest worktree,
   NU pe master.** Master ramane la commit-ul `4c0def1`.

---

## Capitolul 6: Executia planului (Subagent-Driven Development)

Am folosit skill-ul `superpowers:subagent-driven-development`: un
subagent implementator proaspat per task, urmat de un subagent
reviewer (spec compliance + calitate cod) dupa fiecare task, cu bucla
de fix daca review-ul gaseste probleme.

**Ledger complet (sursa de adevar pentru progres):**
```
.worktrees/olx-bot-impl/.superpowers/sdd/2026-09-02-olx-business-laptop-alert-bot/progress.md
```
(Acest fisier + toate brief-urile/rapoartele task-urilor sunt in
`.superpowers/sdd/...` in worktree — ignorate de git, doar workspace
local de lucru. Istoria reala e in commit-urile git.)

### Scanare pre-flight (inainte de Task 1)

Am verificat toate perechile de task-uri pentru conflicte de interfata
(ce produce un task vs. ce consuma urmatorul) — **curat, fara
conflicte**. O singura ruling inregistrata: `.gitignore` exista deja
(din setup-ul worktree-ului) inainte ca Task 1 sa ruleze, deci
implementatorul a fost instruit sa faca **append**, nu overwrite.

### Rezultatul fiecarui task

| Task | Commit(uri) | Review | Note |
|------|-------------|--------|------|
| 1. Scaffolding + config | `b876079` | ✅ curat, aprobat direct | — |
| 2. Parser | `2241ab8` | ✅ aprobat, 2 note minore (deferred) | Regex greedy `.*` + terminator literal `;\n` e mandatat de brief — flagged pentru review final |
| 3. Filtre hard | `bbc9980` | ✅ aprobat dupa verificare | **2 rulings importante** — vezi mai jos |
| 4. Scorer | `fa332c1` → fix → `e7a6b17` | 1 runda de fix, apoi ✅ | Vezi "Fix rounds" mai jos |
| 5. DB dedup | `086ca8c` | ✅ aprobat, 1 nota minora (deferred) | Lipsa type hint pe `score_pct` — cosmetic |
| 6. Notifier | `5622902` → fix → `1546b79` | 1 runda de fix, apoi ✅ | Vezi "Fix rounds" mai jos |
| 7. Scraper HTTP | `02dfb25` | ✅ curat, aprobat direct | — |
| 8. Main + deploy | `a2f415d` | ✅ aprobat, 3 note minore (deferred) | Vezi mai jos |

### Rulings importante (decizii luate in numele user-ului, de verificat)

**Task 3 — doua devieri de la textul literal al brief-ului, ambele
acceptate ca fix-uri corecte la bug-uri reale din plan:**

1. **Model T14 lipsea din lista de modele business.** Brief-ul/spec-ul
   avea doar pattern-uri pentru `T4x0`/`T5x0` (3 cifre: T480, T490,
   T580 etc), dar **user-ul a cerut explicit T14** in cererea
   initiala ("T480, T490, P14s, X13, T14"). Era un gol real in spec,
   nu scope creep. Implementatorul a adaugat `\bt1[0-6]\b` (acopera
   T10-T16). **Cost daca gresit:** minim — pattern-ul e strict
   word-bounded si limitat la un range mic de cifre.
2. **Pattern-ul CPU nu putea matcha NICIUN CPU real.** Pattern-ul din
   brief era `\bi[3579]-1[1-3]\d{2}\b` — dar `\b` (word boundary) nu
   se activeaza niciodata intre doua caractere alfanumerice, si
   aproape toate CPU-urile Intel mobile au un sufix litera+cifra dupa
   numarul de model (ex: "i5-1135**G7**"). Cu alte cuvinte, pattern-ul
   original **nu ar fi matchat niciodata un anunt real** — ar fi
   respins toate laptopurile, indiferent de generatia CPU. Era un bug
   de corectitudine in plan, nu o deviere de scop. Implementatorul a
   facut sufixul optional: `\bi[3579]-1[1-3]\d{2}[a-z]?\d?\b`.
   **Cost daca gresit:** minim — inca respecta strict range-ul de
   generatie 11-13, doar tolereaza sufixul.

**Ambele rulings sunt documentate integral, cu motivatie, in ledger-ul
SDD** (`progress.md`, sectiunea "Ruling: Task 3 regex deviations from
brief").

### Fix rounds (probleme gasite de reviewer, corectate)

**Task 4 (Scorer) — 1 runda de fix, ambele Important:**
1. Potrivire ambigua cand doua modele din `reference_prices` apar
   ambele ca substring in text (ordine nedeterminata din dict) → fixat
   sa prefere **cel mai lung nume de model** care se potriveste
   (deterministic, favorizeaza numele mai specifice).
2. Lipsea protectie la impartire cu zero daca un pret de referinta din
   config e `0` (config gresit) → fixat sa trateze ca "model
   necunoscut" (`{"model": None, "score_pct": None}`).
   Ambele confirmate ADDRESSED la re-review, cu teste noi adaugate.

**Task 6 (Notifier) — 1 runda de fix:**
1. **(Critical)** `MIMEText(body)` fara charset explicit → default
   `us-ascii` → ar fi stricat orice email cu diacritice romanesti
   (ă, â, î, ș, ț) din titlul/descrierea anuntului. Fixat la
   `MIMEText(body, "plain", "utf-8")`.
2. **(Important)** Import `MagicMock` neutilizat in teste → eliminat.
   Confirmat ADDRESSED la re-review (inclusiv un test nou care verifica
   round-trip corect pentru diacritice, cu decodare corecta
   base64/quoted-printable din payload).

### Note minore lasate deliberat neatinse (deferred pentru review final)

- **Task 2 (Parser)**: regex-ul pentru `window.__PRERENDERED_STATE__`
  e greedy si cere terminator literal `;\n` — ar putea rata o pagina
  minificata sau cu alt stil de line-ending. Mandatat explicit de
  brief, deci nu s-a schimbat la nivel de task — de evaluat la review
  final daca merita fix.
- **Task 5 (DB)**: `mark_seen` — parametrul `score_pct` fara type hint
  explicit (`float | None`). Pur cosmetic, nu afecteaza functionarea.
- **Task 8 (Main)**:
  - `logging.basicConfig()` e no-op dupa prima apelare intr-un proces
    Python — inofensiv in productie (un singur proces per rulare
    orara), dar inseamna ca testele care apeleaza `run()` de mai multe
    ori in acelasi proces impart configuratia de logging.
  - Email-ul de "bot oprit" (dupa 3 esecuri) reutilizeaza template-ul
    de subiect al email-ului de oferta normala — functional, dar
    subiectul iese put un pic ciudat ("[OLX Deal] Bot OLX oprit - 0
    lei...").
  - Daca `init_db()` insusi arunca exceptie (ex: cale de fisier
    invalida), aceasta NU e prinsa de logica de failure-tracking
    (care e scopata explicit doar pe "esec de scraping/parsare" per
    spec) — ar opri tot scriptul necontrolat. Caz marginal, in afara
    scope-ului literal al spec-ului.

---

## Capitolul 7: Unde am ramas exact (STOP aici cand reiei)

**Toate cele 8 task-uri sunt complete, commit-uite, testate (30/30
teste treceau la ultimul commit `a2f415d`), si trecute prin review
individual.**

**Urmatorul pas neterminat:** review-ul final pe toata ramura
(whole-branch review), conform skill-ului `subagent-driven-development`
— pasul de dupa ultimul task, inainte de merge. Am generat deja
pachetul de diff pentru asta:
```
.worktrees/olx-bot-impl/.superpowers/sdd/2026-09-02-olx-business-laptop-alert-bot/review-4c0def1..a2f415d.diff
```
(diff complet, 10 commit-uri, ~34KB)

**Am inceput dispatch-ul catre reviewer-ul final (model Opus, cel mai
capabil disponibil, asa cum cere skill-ul pentru review-ul final) —
user a intrerupt exact in acel moment** ca sa ceara acest document de
handoff. **Review-ul final NU a rulat inca.**

### Ce ramane de facut, in ordine, cand user spune sa continui:

1. **Re-dispatch review-ul final** pe toata ramura (branch
   `olx-bot-impl`, de la `4c0def1` la `a2f415d`), model Opus, folosind
   template-ul `code-reviewer.md` din skill-ul
   `superpowers:requesting-code-review`. Diff-ul e deja generat (vezi
   calea de mai sus) — poate fi refolosit direct, nu trebuie
   regenerat.
2. **Daca review-ul final gaseste probleme**: UN singur subagent de
   fix cu toata lista de findings (nu unul per finding), apoi UN
   singur re-review scopat pe diff-ul de fix. Reziduurile se adjudeca
   (parcheaza cu ruling sau rezolva daca sunt load-bearing) — nu exista
   a doua runda de fix dupa asta.
3. **Daca review-ul final e curat**: sterge workspace-ul SDD
   (`rm -rf .worktrees/olx-bot-impl/.superpowers/sdd/2026-09-02-olx-business-laptop-alert-bot`)
   — istoria ramane in git.
4. **Foloseste skill-ul `superpowers:finishing-a-development-branch`**
   pentru a decide ce se intampla cu branch-ul `olx-bot-impl` (merge in
   master, apoi push la `origin/master` — **cere confirmare user
   inainte de push**, conform politicii de actiuni cu efect extern).
5. **Dupa merge**: user trebuie sa faca manual pe mini PC-ul HP:
   - clonare/copiere proiect,
   - `python -m venv venv` + `pip install -r requirements.txt`,
   - copiere `config.example.yaml` → `config.yaml` + completare cu
     email Gmail real + app password (instructiuni complete in
     `README.md`, generat la Task 8),
   - rulare manuala o data (`python -m olx_bot.main`) ca sa verifice
     ca merge,
   - configurare Windows Task Scheduler (pasi exacti in `README.md`).
   **Acest pas final de deploy pe hardware real NU poate fi facut de
   mine — necesita acces fizic la mini PC-ul HP al user-ului.**

### Fisiere cheie de recitit la reluare

- Acest fisier (`HANDOFF.md`).
- Spec: `docs/superpowers/specs/2026-09-02-olx-business-laptop-alert-bot-design.md`
- Plan: `docs/superpowers/plans/2026-09-02-olx-business-laptop-alert-bot.md`
- Ledger SDD: `.worktrees/olx-bot-impl/.superpowers/sdd/2026-09-02-olx-business-laptop-alert-bot/progress.md`
  (contine tot istoricul detaliat task cu task, toate rulings-urile,
  toate rundele de fix — e sursa completa de adevar pentru ce s-a
  intamplat tehnic).
- Cod: tot in `.worktrees/olx-bot-impl/olx_bot/` (pe branch-ul
  `olx-bot-impl`, inca nemers pe `master`).

---

## Capitolul 8: Decizii care merita reconfirmate cu user-ul la un moment dat

Lucruri care au fost decise per judecata mea (rulings SDD) sau prin
raspunsuri rapide ale user-ului, si care ar merita o privire inca o
data cand user-ul are timp:

1. **Lista de modele business e minimala** — doar ThinkPad
   T4x0/T5x0/T1x/X13/X1/P14s/L14, Dell Latitude, HP
   EliteBook/ProBook. Daca user-ul vede pe OLX modele bune care nu
   sunt prinse (ex: ThinkPad L4x0, Dell Precision, HP ZBook), lista
   trebuie extinsa in `olx_bot/filters.py` (`_BUSINESS_MODEL_PATTERNS`).
2. **Tabelul de preturi de referinta e complet gol de continut real** —
   valorile din `config.example.yaml` sunt estimari mele aproximative
   (ex: T480=1800 lei), NU date de piata verificate. User-ul trebuie sa
   le ajusteze cu preturi reale dupa ce vede cateva saptamani de
   anunturi.
3. **Bucket-ul RAM ambiguu (`"12 - 16 GB"`) respinge orice anunt care
   nu mentioneaza explicit "16GB" in text** — asta inseamna ca unele
   laptop-uri cu exact 16GB dar descriere vaga vor fi ratate
   (fals-negativ, documentat ca risc acceptat in spec).
4. **CPU-ul e verificat DOAR prin regex pe text liber** (nicio sursa
   structurata) — fraze neobisnuite pot fi ratate.
