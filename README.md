# PRADATA

Observatori ciutadà gratuït de Pradell de la Teixeta. Una vegada al dia:

1. consulta fonts públiques;
2. detecta referències noves i canvis tècnics;
3. actualitza els fitxers JSON i CSV;
4. regenera la web;
5. la publica a GitHub Pages.

No necessita cap ordinador encès, cap clau d'IA ni cap servei de pagament.

## Abans de començar

Per mantenir el cost en **0 €**, crea el repositori com a **públic**. Això
significa que tant la web com el codi i les dades seran visibles per a tothom.
No hi pugis dades personals ni documents que no siguin públics.

## Posar-ho en marxa

### 1. Crea el repositori

1. Entra a [github.com](https://github.com) i inicia la sessió.
2. Prem **New repository**.
3. Escriu `pradata` com a nom.
4. Marca **Public**.
5. No afegeixis cap altre fitxer i prem **Create repository**.

### 2. Puja aquest paquet

1. Descomprimeix el ZIP.
2. A la pàgina del repositori, prem **uploading an existing file**.
3. Arrossega **tot el contingut** de la carpeta descomprimida, incloses les
   carpetes `.github`, `config`, `data`, `pradata`, `scripts`, `site`, `static`,
   `templates` i `tests`.
4. Prem **Commit changes**.

Important: has de pujar el contingut, no una carpeta exterior que el contingui.
El fitxer `README.md` ha de quedar a la portada del repositori.

### 3. Activa GitHub Pages

1. Obre **Settings** al repositori.
2. Al menú lateral, obre **Pages**.
3. A **Build and deployment**, tria **GitHub Actions** com a font.

### 4. Fes la primera execució

1. Obre la pestanya **Actions**.
2. A l'esquerra, tria **Actualització diària de PRADATA**.
3. Prem **Run workflow** i torna a prémer **Run workflow**.
4. Espera que els dos passos quedin en verd.
5. Obre l'adreça que apareix al pas **Publica a GitHub Pages**.

La web tindrà una adreça semblant a:

`https://EL-TEU-USUARI.github.io/pradata/`

## Funcionament diari

El control s'executa cada dia a les **07.17 h**, hora de
`Europe/Madrid`. També el pots executar manualment des de **Actions**.

Cada execució actualitza:

- `data/records.json`: referències actuals;
- `data/records.csv`: les mateixes dades en format de full de càlcul;
- `data/history.json`: altes i canvis detectats;
- `data/status.json`: estat de cada font;
- `site/`: web estàtica que publica GitHub Pages.

Els fitxers canvien i es guarden automàticament al repositori. Això també deixa
un historial visible a GitHub.

## Fonts oficials

- web municipal;
- apartat municipal de subvencions;
- seu electrònica i transparència;
- BOPT;
- BOE mitjançant la seva API oficial de dades obertes;
- CIDO, fitxa del municipi;
- perfil del contractant;
- Consell Comarcal del Priorat, cerca específica de Pradell;
- Idescat, dades oficials del municipi;
- BASE, informació tributària municipal;
- AOC, actes del Ple;
- AOC, pressupostos i plantilles;
- AOC, convocatòries de personal.

Les fonts es poden canviar a `config/sources.json`.

El Consell Comarcal aporta enllaços nous a les notícies que la seva cerca
oficial relaciona amb Pradell. Idescat i BASE es vigilen com a pàgines de
referència: un canvi tècnic queda registrat per revisar, però no es converteix
automàticament en una afirmació pública sense data i contingut verificables.

Les tres fonts de dades obertes de l'AOC es consulten amb el codi oficial de
l'Ajuntament (`4311530008`). Només incorporen registres dels darrers vuit dies,
però els marquen com a verificats perquè l'API oficial ja aporta municipi, data,
títol i enllaç. Això permet recuperar publicacions que hagin aparegut durant els
set dies anteriors sense omplir el web amb tot l'històric.

## Àmbit territorial de la cerca

La cerca diària combina el nom complet **Pradell de la Teixeta**, el nom curt
**Pradell** i els identificadors oficials del municipi. També consulta
**Teixeta** al BOPT i als sumaris del BOE, però només conserva aquestes
coincidències ampliades quan hi ha context territorial rellevant: coll, serra,
carreteres, ferrocarril, energia, incendis, aigua o camins, entre altres.

Per reduir falsos positius, s'exclouen adreces d'altres municipis que només
utilitzen «Pradell de la Teixeta» com a nom de carrer. Aquest filtre amplia la
cobertura de l'entorn sense considerar qualsevol aparició de «Teixeta» com una
publicació relacionada amb Pradell.

## Què vol dir cada estat?

- **Verificat amb font**: registre inicial comprovat amb una publicació
  institucional identificada.
- **Detecció automàtica**: el motor ha trobat un títol o un enllaç en una font
  pública; cal obrir l'original abans d'interpretar-lo.
- **Consulta parcial o no disponible**: aquella font no s'ha pogut llegir del
  tot. No significa que no hi hagi publicacions.

El fitxer `data/status.json` diferencia `successful_sources` (fonts llegides
completament) de `responsive_sources` (fonts que han respost completament o
parcialment). Així un avís no es presenta com una consulta completa.

## Limitacions importants

PRADATA és un inventari automatitzat, no una certificació jurídica ni una
auditoria completa. Aquesta versió:

- llegeix títols, enllaços i sumaris accessibles;
- no interpreta automàticament el contingut de tots els PDF;
- no considera una fallada de cerca com a prova d'absència;
- no acusa cap persona ni administració;
- manté sempre l'enllaç a la font original, que és la que preval.

Algunes pàgines canvien d'estructura amb el temps. Si una font deixa de
funcionar, el **Radar de fonts** ho mostrarà.

## Cost

El projecte està pensat per a un repositori públic, executors estàndard de
GitHub Actions i GitHub Pages. En aquesta configuració no incorpora cap
dependència de pagament. Evita activar executors grans o serveis externs.

GitHub pot desactivar programacions de repositoris públics sense activitat
durant un període llarg. Si algun dia passa, entra a **Actions** i torna a
activar o executar manualment el control.

## Prova opcional en un ordinador

No és necessari per al funcionament diari. Si algú amb coneixements tècnics vol
provar el paquet abans de pujar-lo:

```text
python scripts/collect.py
python -m unittest discover -s tests -v
python scripts/check_output.py
```

El BOPT es consulta a partir del seu calendari oficial: PRADATA només demana
les dates que el mateix butlletí mostra com a publicades. Això evita convertir
els errors HTTP 500 dels dies sense edició en falsos avisos de cobertura, sense
ocultar cap error real d'una data publicada.

Després pot servir la carpeta `site` amb qualsevol servidor web local.

## Avisos automàtics a Telegram

El workflow diari també pot avisar el canal públic
[`@pradellteixeta`](https://t.me/pradellteixeta). El publicador consulta
exclusivament `https://pradell360.cat/api/pradata-verified`: una detecció
pendent o sense data de publicació verificada no es pot enviar.

Proteccions incorporades:

- l'historial existent abans de l'activació queda registrat com a ja vist i no
  es publica retrospectivament;
- cada identificador només es publica una vegada;
- les publicacions sobre un mateix tema, com la TV-3223, s'agrupen;
- hi ha un màxim de tres missatges per execució i l'excés es converteix en un
  resum;
- cada avís mostra la data real de publicació i la data de detecció;
- els enllaços porten a la fitxa de Pradell360, no directament a la font final;
- el testimoni del bot no es desa mai al repositori ni als logs.

### Configuració segura del bot

1. Crea el bot amb `@BotFather`.
2. Afegeix-lo com a administrador del canal i concedeix-li únicament el permís
   **Publicar missatges**.
3. A GitHub, obre **Settings → Secrets and variables → Actions**, crea el secret
   `TELEGRAM_BOT_TOKEN` i enganxa-hi el testimoni privat.
4. Canvia `enabled` a `true` a `config/telegram.json`. El camp `channel_url` defineix l’enllaç de subscripció que s’afegeix una sola vegada a cada notificació.
5. Executa manualment **Actualització diària de PRADATA** una vegada.

El fitxer `data/telegram-state.json` conserva només identificadors públics i els
identificadors de missatge retornats per Telegram. No conté cap secret. Si cal
aturar els avisos immediatament, canvia `enabled` a `false`; la recollida i la
publicació de Pradell360 continuaran funcionant.

### Com verificar-ho

- a **Actions**, els tres treballs `Consulta les fonts i prepara la web`,
  `Publica a GitHub Pages` i `Avisa al canal de Telegram` han d'acabar en verd;
- el log de Telegram indica quants registres verificats, elegibles, agrupats i
  enviats hi ha, sense mostrar el testimoni;
- una passada sense novetats ha d'indicar `0 novetats elegibles` i no ha
  d'afegir cap missatge al canal;
- les proves locals es poden executar amb
  `python -m unittest discover -s tests -v` i la simulació, que no envia res,
  amb `python scripts/publish_telegram.py --dry-run`.

El Bot API de Telegram, els executors estàndard d'un repositori públic i aquest
publicador amb biblioteca estàndard de Python no requereixen cap servei de
pagament.

## Control setmanal de salut de Pradell360

El workflow `.github/workflows/salut-setmanal.yml` s’executa cada dilluns a
les 08.30 h (Europe/Madrid) i també admet execució manual. Revisa, sense
modificar ni publicar res, la portada, `robots.txt`, el sitemap, l’API de
PRADATA, una fitxa, un dossier, la pàgina 404, la cobertura de les 13 fonts,
l’estat antirepetició de Telegram i una mostra de fins a 40 enllaços oficials
i interns.

Cada execució incorpora el resum a GitHub Actions i conserva durant 30 dies
els artefactes `health-report.json` i `health-report.md`. No conté cap pas de
desplegament ni cap credencial o enviament a Telegram. Els bloquejos 403/429 o
de xarxa consten com a no concloents; un enllaç 404/410, un error de servidor,
dades obsoletes o una fallada estructural fan fallar el control.

Prova local:

```text
node --test tests/health-check.test.mjs
node scripts/health-check.mjs
```

## Llicència

El codi es distribueix amb llicència MIT. Els documents i les dades de les
fonts conserven les seves pròpies condicions de reutilització.


## Estat operatiu

L’execució diària conserva la revisió retrospectiva de 7 dies. Telegram només s’executa després que GitHub Pages confirmi que serveix el mateix `records.json`; el publicador espera també l’API de Pradell360 i només registra l’èxit després de la confirmació de Telegram.

El 21 d’agost de 2026 s’han comprovat Pages i Pradell360. Hi havia 22 registres verificats i cap novetat elegible, així que no s’ha publicat cap missatge de prova.
