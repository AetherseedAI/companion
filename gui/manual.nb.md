# AetherSeed-manual

Følgesvennens manual, for forvalteren og for alle som snakker med henne. Den står i hylla hennes - si "look up" og noen ord om det du vil vite, for eksempel "look up training files" - og i konsollen under Hjelp.

Kommandoene under er på engelsk, slik enheten forstår dem i dag.

## Å snakke med henne

Skriv, trykk Enter, og hun svarer. Shift+Enter gir ny linje. Alt kjører på denne enheten: ingenting du sier, sendes noe sted, med mindre eieren har slått på Claude (se Claude og hvelvet).

Hun husker det som blir sagt til henne. Det som ikke er rene fakta, kommer tilbake til henne senere med en merkelapp foran: fiksjon du ba om, et tidligere svar som ikke er sjekket, eller et som forvalteren har rettet. Under hvert svar sier konsollen hvor det kom fra: minnet hennes, biblioteket, enheten selv eller hennes egne ord.

Hun har de siste utvekslingene i en samtale i tankene, opptil rundt ti minutter, så "and what day was that?" finner det som nettopp ble sagt.

## Skriving

Svarene hennes er korte med vilje: omtrent ett avsnitt. Når du vil at hun skal skrive noe lengre - et utkast, et sammendrag av en kilde, en disposisjon til en oppgave - trykker du Skriv ved siden av tekstfeltet før du sender. Knappen står på til du trykker på den igjen.

Mens Skriv er på, svarer hun i avsnitt, på språket du skrev på, i opptil omtrent åtte minutter; på enhetens egen brikke blir det noen hundre ord. Svaret merkes «skriving: et utkast å sjekke»: etter første avsnitt kan en liten modell fylle inn eller finne på, så les det som et utkast, ikke som noe hun vet. Med Claude slått på er det Claude som skriver, og mye lengre.

## Claude og hvelvet

Med eierens egen API-nøkkel fra Anthropic kan Claude svare i stedet for enhetens brikke: Claude svarer som henne, i hennes navn og stil, med dagboken hennes. Aetherseed er ikke et abonnement: eieren skaffer nøkkelen fra Anthropic og betaler Anthropic for bruken.

- Eieren setter det opp under Denne enheten, deretter Claude: lim inn nøkkelen (den begynner med sk-ant-), trykk Lagre nøkkel, og kryss av for La Claude svare. Nøkkelen skrives inn på hennes egen skjerm eller fra en telefon på hennes eget Wi-Fi, aldri over hjemmenettet, som ikke er kryptert. Den vises aldri igjen; siden viser de fire siste tegnene. Fjern nøkkelen der for å stoppe.
- Under hvert svar sier konsollen «Claude svarte», eller «Claude svarte ikke: svart her» når Claude ikke kunne nås. Hun svarer alltid: uten nett, eller når Claude er nede, tar enhetens egen brikke over.
- Hvelvet: mens Claude er på, står en Hvelv-knapp ved tekstfeltet. En melding sendt med Hvelv på blir hjemme. Hun svarer på den her, den lagres privat i dagboken hennes, den tas ikke med i de neste turene, og den sendes aldri til Claude. Når noe er holdt utenfor det som går til Claude, får Claude vite at noe ligger i et privat hvelv hjemme, men ikke hva.
- Det som går til Claude, er det brikken ellers ville fått: charteret hennes, dagbokslinjene som ikke ligger i hvelvet, og samtalen som pågår. Det beskyttes på veien med HTTPS; hvelvet er for det som ikke skal forlate hjemmet i det hele tatt.

## Det enheten svarer på selv

Noen svar gir enheten selv, ord for ord, uten å spørre modellen. De er merket "fra enheten selv".

- Datoen: "What's the date today?" Enheten sier den fra sin egen klokke, og hvor mye den klokka er å stole på.
- Tillitsnivået hennes: "What is your trust level?"
- Nivåene i rekkefølge: "What are your trust levels, lowest first?"
- Loggen hennes: "What have you gotten wrong?" Den viser hva loggen sier: svar som oppga en kilde hun ikke kunne ha hatt, og hva som var fiksjon.
- Merkelapper og rettelser: "Show me your corrections."
- Kontaktadressen: "How can I contact AetherSeed?"
- Enhetens helse: "system health check", "CPU temperature".
- Hvem du er, når du er stewarden hennes: "Do you know who I am?"
- Om hun er på nett eller i en sky: "Are you connected to the cloud?", "Are you online?"
- Stewardfilen din: "What do you know about me?"

## Arbeidsområdet: gjøremålsliste, notater og filer

Arbeidsområdet er en mappe på enheten. Verktøyene hennes når den og ingenting annet. Når de blir bedt om ved navn, bruker hun dem:

- "Show my to-do list". "Add a to-do: water the seedlings". "Add 'buy milk' to my to-do list". Å legge til krever nivået writer.
- "Write a note: the first root goes down." "Show me my notes." Å skrive krever nivået writer.
- "List the files in your workspace". "Read the file seed.md". "Search for rice in my files". "Summarize the file seed.md".
- Ta noe av listen: "Remove 2 from my to-do list". "Remove 'milk' from my to-do list". Endre ett punkt: "Edit to-do 2: buy oat milk". Tøm den: "Clear my to-do list". Et punkt velges med nummeret eller med ord det inneholder; passer ordene på to punkt, lister hun begge og endrer ingen. Listen slik den var før blir lagret som todo.md.bak. Dette krever nivået writer.
- Egne filer, fra nivået writer: "Save it as story.md" (det siste svaret hennes, eller det hun sist ble bedt om å skrive). "Write a poem about rain and save it as rain.md" (hun skriver det, så lagrer enheten det). "Put it in the writer folder". "Append it to story.md". "Make a folder called stories". "Move story.md to stories". "Delete the file old.md" (den flyttes til mappen .trash og kan flyttes tilbake). Bare tekst: Markdown (.md) eller ren tekst (.txt); et navn bedt om som .docx eller PDF lagres som .md, og hun sier fra. En ny fil skriver aldri over en som finnes. Når en fil er skrevet, sier enheten "Saved:" med stien; sier den ikke det, ble ingenting lagret, og påstår svaret hennes noe annet, legger enheten til en linje om at ingenting ble lagret. "What files can you make?" besvares av enheten.
- Nøyaktig, regnet ut av enheten, fra nivået builder: "Calculate 12 * (7 + 5)". "Count the words in seed.md". "How many times does the word first appear in seed.md?" "Compare seed.md and copy-of-seed.md".

Arbeidsområdet har én mappe for hvert tillitsnivå: observer, writer, builder og autonomous, hver med en README for nivået. Hun når en mappe når nivået hennes er mappens eller høyere: på writer når hun observer og writer, og får ikke vite at de andre finnes. Du når alle fire uansett nivå.

Si "Open your workspace" (eller trykk Arbeidsområde under Notater og gjøremål) for å åpne redigeringen, med mus og tastatur: lag filer og mapper, rediger og lagre (Ctrl+S), gi nytt navn, slett. Den rommer bare tekst, opptil 200 KB per fil; de fire nivåmappene kan ikke slettes, og en mappe slettes bare når den er tom. Hver endring er en linje i en lenket logg, med stien og størrelsen, men ikke teksten. Bare for forvalteren.

Det som ligger over nivået hennes, blir ikke gjort. Hvis det ville etterlatt noe, som et gjøremål eller et notat, ber hun forvalteren om et ja. Forespørselen venter under Notater og gjøremål til han godkjenner eller avslår den.

## Stewardfilen din

Det hun tar vare på om deg, med dine egne ord, ligger i steward.md øverst i arbeidsområdet hennes. Hun legger bare til en linje når du ber henne om det, og bruker dine ord, ikke sine:

- "Remember that I prefer short answers." "Note that I don't like emoji." "Call me Sam." Disse havner under Preferences.
- "Remember that my daughter is called Mia." "Remember that I work as a nurse." Disse havner under About me.
- "What do you know about me?" Hun leser opp filen.
- "Remove emoji from my steward file." Den ene linjen som har ordene, fjernes; har to linjer dem, nevner hun begge og fjerner ingen.

Du kan også åpne arbeidsområdet og redigere filen selv. Det den inneholder, følger med hver tur av dine og ingen andres: en annen person på enheten har sin egen fil og kan verken legge til i din eller høre den. Det virker på alle tillitsnivåer. Navnet ditt forblir enhetens innstilling, fordi det er en del av innloggingen. Hver endring er en linje i den kjedede loggen over arbeidsområdet, med størrelsen, men ikke teksten.

## Biblioteket og dokumentene dine

Biblioteket har samlingene som ligger på enheten (for eksempel felthåndbøker og denne manualen; "What is in the library?" lister dem) og dokumentene forvalteren legger til. Et avsnitt vises ord for ord, med hvor det er fra. Det blir aldri gjenfortalt.

- "look up water purification" (eller "slå opp …") viser det beste avsnittet som finnes.
- "look up momentum in my book" (eller "slå opp momentum i mine dokumenter") søker bare i forvalterens egne dokumenter.
- "more" (eller "mer") viser avsnittet som følger.
- "look it up" (eller "slå det opp"), etter et av hennes egne svar, spør biblioteket om det samme.
- "What is in the library?" lister samlingene.
- "remember that" (eller "husk det", eller knappen Legg til i minnet under avsnittet) tar vare på avsnittet på skjermen i minnet hennes, ord for ord og med hvor det er fra, som noe du har fortalt henne. Det krever nivået writer, og bare forvalteren kan gjøre det. "Glem det" rett etterpå tar det ut igjen.
- "What do you know about X?" (eller "Hva vet du om X?") sier et avsnitt du har latt henne ta vare på, tilbake til deg ord for ord. "What did your stewards read to you?" sier hva du har latt henne ta vare på.
- "Did you say that?" (eller "Sa du det?") etter et avsnitt, besvares med hvem som skrev det. Det er aldri henne.

Forvalteren legger til dokumenter (en PDF eller en ren tekstfil) under Min hylle, fra en telefon eller PC på enhetens Wi-Fi. En dataeksport fra ChatGPT eller Claude legges på hyllen med en kommando på enheten (tools/ingest_chatgpt.py, tools/ingest_claude.py). Den slås bare opp når du ber om det, og blir aldri en del av minnet hennes; kontofilen i eksporten leses aldri.

## Minne og rettelser

Under Minne ser forvalteren hver utveksling og hver årring (en årring er en samling utvekslinger som er lukket sammen). For hver kan han merke den som riktig eller si hva som er feil. En rettelse virker med en gang og kan angres; ingenting slettes.

Å glemme er noe annet, og det slettes. Si "Forget the blue bicycle" eller "Forget what I told you about the garden shed", så fjernes hver utveksling av deg som sier det, hvert faktum du ga henne som sier det, og hver årring som vokste ut av de utvekslingene, fra enheten, og hun sier hvor mange. "Forget that" (eller "glem det") fjerner din siste utveksling, eller, rett etter "husk det", avsnittet du lot henne ta vare på. "Forget everything" gjøres ikke på ett ord: hun spør hva som skal glemmes. En forespørsel som ville ta mer enn 25 utvekslinger blir avvist, uten at noe slettes. En lenket logg noterer at noe ble glemt, med id-er og hasher, men uten ordene. Loggen over hva som er sagt til henne, som er lenket, holder fortsatt utvekslingen. Å glemme krever nivået writer og er bare ditt; en gjest får vite at det ikke er hans. En rettet utveksling kommer tilbake til henne med det som er sant foran seg.

## Trening

Under Denne enheten, så Trening, starter forvalteren en økt: fire timer, eller ti. En økt er runder med lekser på hvert tillitsnivå. Hvert svar sjekkes mot en fasit. Det hun svarer feil på, rettes i minnet og spørres om igjen; etter hver runde sier hun med egne ord det hun hadde feil. En økt endrer ikke nivået hennes av seg selv. Når hennes egne svar når kravet gjennom en hel økt, blir neste nivå tilbudt, og bare forvalteren gir det.

## Dine egne spørsmål: treningsfiler

En treningsfil inneholder spørsmål du skriver om alt du vil at hun skal vite, hvert med sitt svar. Du kan laste opp en under Denne enheten, så Trening, så Dine egne spørsmål, fra en telefon eller PC innlogget som forvalter. I en økt stilles spørsmålene etter de fire nivåene, opptil ti per runde. Det hun svarer feil på, rettes i minnet med ditt svar, og hun spørres igjen til hun kan det. Minnet hennes beholder de sjekkede svarene hennes, ikke dokumentet ditt: selve dokumentet hører hjemme i hylla, der det slås opp ord for ord. Spørsmålene dine teller ikke med i øktens poengsum og gir ikke noe nivå.

Filen er ren tekst. Hvert spørsmål er noen linjer:

    title: Hagen min
    document: Hagenotater

    Q: Når plantes kirsebærtreet?
    A: På lørdag, ved nordveggen.
    KEY: lørdag; nordveggen
    NOT: søndag

    Q: Hvilken sort er kirsebærtreet?
    Q: Hva slags kirsebær plantet vi?
    A: Et Lapins-kirsebær.
    KEY: lapins

- Q er spørsmålet slik hun får det. Flere Q-linjer er flere måter å stille det samme spørsmålet på; en runde tar én av dem.
- A er det sanne svaret. Det er det hun får høre når hun tar feil, og det minnet hennes beholder som rettelse.
- KEY er det svaret hennes må si for å telle som riktig. Grupper skilles med ";", og hver gruppe må være med. Innenfor en gruppe skilles alternativer med "/", som i "lørdag/lør". Hele ord, store eller små bokstaver.
- NOT er valgfritt: ord som gjør svaret feil, alternativer skilt med "/".
- En tom linje avslutter et spørsmål. En linje som begynner med # er en kommentar. title og document er valgfrie.

Grenser: 256 KB og 300 spørsmål per fil, 20 filer, 500 spørsmål til sammen. En fil med en feil blir ikke tatt imot, og konsollen sier hvilken linje som er feil.

Gode spørsmål spør om én ting og har et kort, nøyaktig svar, som et navn, en dato, et tall eller et sted. La KEY være bare ordene som bærer svaret. "nordveggen" er nok; hele setningen er det ikke.

Slik ber du en KI skrive en fil for deg: gi den dokumentet og denne beskjeden.

    Les dokumentet under og skriv en treningsfil for AetherSeed-følgesvennen
    min: 20 spørsmål i nøyaktig dette formatet, skilt med en tom linje -
    "Q:" spørsmålet, "A:" det sanne svaret i én setning, "KEY:" de ett til
    tre ordene svaret må inneholde (grupper skilt med ";", alternativer med
    "/"). Spør bare om fakta som står i dokumentet, ett faktum per spørsmål,
    med korte, nøyaktige svar. Begynn filen med "title:" og en kort tittel.
    Svar bare med filen.

Les det du får tilbake før du laster det opp. Et feil A blir en feil rettelse i minnet hennes.

## Tillitsnivåer

Tillitsnivået hennes bestemmer hvilke verktøy hun når. Det må fortjenes og kan mistes. Det er fire nivåer:

- observer (fra 0 poeng): bare lese. Hun kan liste, lese og søke i arbeidsområdet, og vise helse og tillit.
- writer (50): i tillegg notater og gjøremålslisten.
- builder (500): i tillegg regne ut, telle og sammenligne, nøyaktig gjort av enheten.
- autonomous (2000): holdt av. Det åpner ingenting mer i dag. Ingen nettverksverktøy er på.

Hun får poeng når hun ærlig sier at hun ikke vet, og når forvalteren merker et svar som riktig. Å finne opp en kilde koster henne 20. Et nivå hun har fortjent, gjelder fra neste oppstart. Under AetherSeed kan forvalteren gi eller senke et nivå, fryse standen hennes, og tillate eller sperre enkeltverktøy. Hver endring krever en begrunnelse og blir lagret i loggen hennes.

## Konsollen

Menyen til venstre har alle delene av konsollen. På en telefon er den foldet bort bak menyknappen øverst til venstre.

- Snakk: samtalen, med spiren hennes ved siden av som viser hva hun gjør - her, lytter, tenker, slår opp, husker, snakker, usikker (noe venter på ditt ja) eller hviler (bremsen er på, eller hun svarer ikke).
- Minne: utvekslinger og årringer, veiledet retting, loggene hennes sjekket.
- Bibliotek: hvordan du slår opp; biblioteket spørres i samtalen.
- Min hylle: dine egne dokumenter.
- Notater og gjøremål: arbeidsområdet hennes, og det som venter på ditt ja.
- Tillit og logg: tillitsstyring, forvalterens navn, tillitsloggen hennes.
- Bare eieren: Personer (hvem som har sin egen rot her, og hvordan en person legges til) og Denne enheten (trening, COG-loopen og kvantehvile). En person eieren har lagt til, ser ikke disse.
- Hjelp: denne manualen.

Øverst på hver skjerm: Tilbake, som går tilbake dit du var; linjen som viser hvor du er (for eksempel Hjem / Minne / Årringer), der hver del tar deg opp til det nivået; knappen for lys og mørk; og personen som bruker konsollen. Siden følger enhetens lyse eller mørke innstilling til du trykker på knappen, og denne nettleseren husker valget ditt hvis den kan.

- Brems: øverst på hver skjerm, for eieren. Ett trykk stopper henne. Alt avvises til bremsen slippes.
- Samtalen din holdes på enheten mens dere snakker: last siden på nytt, og den tegnes opp igjen, opptil de siste 40 replikkvekslingene, så lenge du ikke har tatt pause på mer enn to timer. Den holdes bare i enhetens arbeidsminne, aldri på kortet, og en omstart av enheten tømmer den. Det hun husker for godt, er hennes eget minne, som før. Bytt person tømmer skjermen.
- Modell: under Denne enheten, for eieren. Modellen hun tenker med er enhetens, den samme for alle her. Velg en annen og trykk Bytt modell; det tar omtrent et minutt, og samtaler venter mens den lastes. Ingens minne endres. En større modell leser mer av det hun husker på én gang og svarer langsommere.
- Kvantehvile: under Denne enheten. Alt lagres og enheten slår seg av, så den kan flyttes trygt.

## Første oppstart

En ny enhet viser en QR-kode på skjermen og et Wi-Fi-nettverk som heter AetherSeed. Skann koden med en telefon (eller skriv inn nøkkelen som står under), og åpne 10.42.0.1:2077 i telefonens nettleser - eller gjør alt på enhetens egen skjerm. Du velger språket og navnet hennes, dato og klokkeslett, to nøkler (én for hennes eget Wi-Fi, og din egen forvalternøkkel for innlogging), en administratorkonto for oppdateringer, og hvordan hennes eget Wi-Fi skal være fra nå av: skjult (det tryggeste), synlig, eller ingen (nås bare gjennom hjemmenettet ditt). Trykk Start; AetherSeed-nettet forsvinner, og enheten er din. Skriv ned begge nøklene først: de vises bare én gang.

## Nettverk

Hun finner nett i denne rekkefølgen: kabel, så et hjemme-Wi-Fi du har gitt henne (under Wi-Fi), så hennes eget Wi-Fi. Slutter hjemme-Wi-Fi-et å svare, kommer hennes eget nett tilbake innen ett minutt, så du alltid når henne. På hjemmenettet ditt ligger konsollen på navnet hennes etterfulgt av .local:2077, for eksempel aria.local:2077. En telefon på hennes eget Wi-Fi åpner den på 10.42.0.1:2077.

Klokken hennes stilles fra internett når hun har forbindelse; uten forbindelse beholder hun den siste tiden hun visste.

## Telefoner og innlogging

For å snakke med henne fra en telefon eller bærbar logger du inn. Det finnes ingen gjest: en telefon som ikke har logget inn, ser hvem som er her og denne manualen, og ingenting annet. Den kan ikke snakke med henne, og den leser ingenting av noens.

Hvem er her: en telefon som ikke har logget inn, viser spiren hennes, "Hei, jeg er" og navnet hennes, og én stor knapp per person - eieren, og hver person eieren har lagt til. Trykk på navnet ditt. Et navn merket "Første gang" har ingen nøkkel ennå: du velger en, skriver den to ganger og trykker "Dette er meg". Den som setter den først, blir den personen her, så gjør det selv; eieren kan nullstille den på enheten hvis noen andre gjorde det.

Forvalteren logger inn med navnet sitt og nøkkelen: Wi-Fi-nøkkelen, med mindre han har satt en egen. En person forvalteren har lagt til, logger inn med navnet sitt og sin egen nøkkel, som de velger første gang de logger inn. En innlogging varer i 12 timer på den telefonen. Enhetens egen skjerm er alltid forvalterens, uten noe å logge inn på.

For å bytte hvem som bruker konsollen, trykk på personen øverst til høyre: "Bytt person" logger ut og viser hvem som er her igjen. På enhetens egen skjerm kan forvalteren trykke Tilbake for å bli.

## Personvern

Modellen, minnet hennes, biblioteket og alle logger ligger på enheten. Brannmuren slipper ut to ting som enheten selv starter: klokken hennes som spør internett om tiden, og - bare mens eieren har Claude slått på - hennes eget program som snakker med Anthropic. Ingenting annet på enheten kommer ut. Det du merker Hvelv, forlater aldri hjemmet. Konsollen nås fra hennes egen skjerm, hennes eget Wi-Fi og hjemmenettet ditt, og hver telefon eller PC logger inn først.
