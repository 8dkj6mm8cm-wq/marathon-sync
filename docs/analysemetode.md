# Analysemetode: marathonprogression
Autoritativ instruktion for de planlagte Claude-opgaver. Ligger i repoet, så en frisk
session altid kan hente den. Ret her, og næste kørsel bruger den nye version.
Kalibreret mod faktiske data 26-08-2026. Alt nedenfor om feltnavne er verificeret mod
en rigtig payload, ikke antaget.
## Rammer
- **Løb:** Copenhagen Marathon, søndag 9. maj 2027
- **Mål:** 3:45:00, svarende til 5:20/km
- **Plan:** 37 uger. Uge 1, Fase 1 "Genstart" startede 25-08-2026
- **Athlete:** `i669726`
- **Udstyr:** Garmin Vivoactive 3. Optisk håndledspuls, ingen brystrem, ingen løbepower.
  Pulsen er træg i starten af intervaller og støjer ved høj intensitet. Vurder
  intervalpas primært på tempo, ikke på puls.
## Hent data
```bash
curl -sSL "$REPO_RAW/data/latest.enc" \
  | openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -base64 -A -pass "env:DATA_PASSPHRASE" \
  | gunzip > payload.json
```
Læs `data/status.json` først. Er `all_ok` falsk, eller er `generated_at` mere end
36 timer gammel, så skriv det øverst i outputtet og analyser på det data der er.
**Regn i Python.** Hvert tal i outputtet skal komme fra en beregning på payloaden.
Gæt aldrig et tempo, en ugesum eller en trend.
## Zoner og tærskler
Fra `athlete.sportSettings` for Run. Verificerede værdier fra intervals.icu:
| Zone | Navn | Puls |
|---|---|---|
| Z1 | Recovery | under 149 |
| Z2 | Aerobic | 149 til 158 |
| Z3 | Tempo | 158 til 167 |
| Z4 | SubThreshold | 167 til 176 |
| Z5 | SuperThreshold | 176 til 181 |
| Z6 | Aerobic Capacity | 181 til 186 |
| Z7 | Anaerobic | 186 til 195 |
LTHR 177, maks-puls 195. Dette er intervals.icu's egen model, brugt af tjenesten selv
til dens egne grafer. Den er **ikke** den model analysen styrer efter, se næste afsnit.
### Den autoritative zonemodel (Andreas' beslutning, 29-08-2026, endelig)
Analysen bruger udelukkende Garmins model: **zone 2, den aerobe, rolige zone, er puls
118 til 138 slag i minuttet.** Det er en beslutning, ikke et beregningsresultat, og den
er endelig. Brug dette bånd hver gang et pas skal vurderes som i eller uden for zonen.
Nævn intervals.icu's eget bånd (149 til 158) kun hvis det er nødvendigt for at forklare
en afvigelse i tal som tjenesten selv viser, aldrig som et konkurrerende alternativ i
vurderingen. Antag ikke længere at "zone 2" i en planbeskrivelse kan betyde noget andet.
**Regel for analysen:** rapporter altid puls i slag per minut ved siden af enhver
zonevurdering, så konklusionen står uafhængigt af modellen.
### Hvor usikre er tallene
Tærskelpulsen 177 svarer til 90,8 procent af maksimalpulsen 195, og zonegrænserne
ligger på 84,2, 89,3, 94,4, 99,4, 102,3, 105,1 og 110,2 procent af den. Det er
nøjagtigt intervals.icu's standardafledning. **Tærsklen er altså regnet ud fra
maksimalpulsen, ikke målt**, og det gælder uanset hvilken zonemodel man ser på.
Maksimalpulsen 195 er til gengæld rimeligt underbygget: højeste observerede puls i
historikken er 189 under et 10 km-løb 17. juni 2026. Den ægte maksimalpuls ligger
sandsynligvis mellem 190 og 197.
Konsekvens: begge modellers grænser hviler på estimater, ikke på en gennemført test.
Anbefal en 20 eller 30 minutters tærskeltest, når grundformen bærer det. Sig indtil da
eksplicit, at zonegrænser er usikre, og læn dig på tempo og absolutte pulstal frem for
zonenumre alene.
### Fysiologisk kontekst, ikke en konkurrerende zone
Nedenstående er regnet på payloaden 26-08-2026 og er en observation at holde øje med,
**ikke en ny operativ grænse.** Zone 2 = 118 til 138 gælder uanset denne observation.
**Afkobling på lange ture.** Beregnet fra `icu_intervals`, første mod anden halvdel:
| Dato | Varighed | Snitpuls | Afkobling |
|---|---|---|---|
| 23-08 | 80 min | 134 | +2,4 % |
| 25-08 | 36 min | 134 | -2,1 % |
| 21-08 | 30 min | 136 | +0,9 % |
| 20-08 | 9 min | 148 | +15,2 % |
De tre første er evidens for at **puls 134 ligger komfortabelt under LT1**. En
80-minutters tur med kun 2,4 procent afkobling er aerobt arbejde med god margin.
Den fjerde skal ikke tolkes: ni minutter er for kort til at pulsen når ligevægt, og
tallet afspejler pulsens træghed, ikke fysiologi. Brug aldrig ture under 40 minutter
til afkobling.
**Puls mod tempo.** Lineær regression, genberegnes løbende på de seneste løb:
```
HR = 208,0 - 9,9 * tempo i min/km      R2 = 0,54 (regning 26-08, tolv løb siden 1. maj)
```
R2 er middelmådigt, og en genberegning 29-08 på tretten løb gav et andet udtryk
(R2 0,52). Brug modellen til at anslå størrelsesordener, aldrig til at fastslå et tal,
og genberegn den hver uge.
Denne evidens peger på at den reelle aerobe tærskel (LT1) muligvis ligger noget over
138, måske nærmere 145 til 152. Nævn det som baggrund højst én gang om ugen. Skift
først den operative grænse, hvis en gennemført tærskeltest bekræfter det.
## Kendte huller i data
Tjek disse hver gang, men rapporter dem højst én gang om ugen, ikke dagligt.
| Felt | Status | Konsekvens |
|---|---|---|
| `wellness[].restingHR`, `.hrv`, `.weight` | Tomme i alle records | Ingen restitutionsanalyse. `icu_garmin_download_wellness` er slået til, men `icu_garmin_wellness_keys` er tom. Andreas kan vælge wellness-felter under intervals.icu → Settings → Garmin, eller overveje en Oura-integration, som intervals.icu understøtter direkte |
| `wellness[].sleepSecs` | Kun 2 records | Ingen søvnanalyse |
| `activity.decoupling`, `.icu_efficiency_factor` | Null | Beregn selv, se nedenfor |
| `activity.compliance` | Altid 0.0 | Ubrugelig. Sammenlign selv mod `events[].description` |
| `events[].icu_training_load` | Null | Ingen planlagt belastning at måle mod. Brug varighed og tempo fra beskrivelsen |
| `workout_doc.steps` | Tom liste | Passene er fritekst, ikke strukturerede |
| `wellness[].vo2max` | Tom i alle 241 records | Intet direkte VO2 maks fra platformen. Se afsnittet om VO2 maks-estimat |
Vivoactive 3 måler ikke HRV-status. Forvent aldrig HRV, uanset indstillinger.
## Sådan læses et planlagt pas
`events[]` med `category: "WORKOUT"`. Ordinationen står som fritekst i `description`,
for eksempel:
> Rolig tur, 20 min, zone 2 (samtale-tempo, ca. 6:15-6:45/km)
Udtræk varighed og tempointerval fra teksten. Match til den udførte aktivitet på dato
og `type: "Run"`. Er der flere løb samme dag, tag det der ligner ordinationen mest.
Zoneordet i teksten refererer altid til den autoritative model (118 til 138), uanset
hvilken formulering planen selv bruger.
## Beregninger
**Tempo.** Brug `gap` (grade adjusted pace) frem for `average_speed`, når ture
sammenlignes på tværs af terræn. Begge er i m/s. Tempo i min/km er `1000 / (v * 60)`.
Andreas løber periodevis i kuperet norsk terræn, hvor råt tempo er misvisende.
**Intensitetsfordeling.** `icu_hr_zone_times` er bundet til intervals.icu's egne
grænser (149, 158, 167 ...), ikke til den besluttede 118-138-grænse, og kan derfor
ikke bruges direkte. Beregn i stedet fra `icu_intervals` (auto-omgange med
`average_heartrate` og `moving_time`): summer omgangstid med snitpuls under 138 mod
omgangstid derover. Det er en tilnærmelse på omgangsniveau, ikke sekund for sekund,
men det er den bedste tilgængelige opløsning for de pas hvor intervaldata er hentet.
For pas uden intervaldata, brug hele løbets gennemsnitspuls som en grovere erstatning.
Rapporter andelen af tid under 138 som "lav intensitet", mål omkring 80 procent i en
opbygningsfase. `activity.polarization_index` findes også og kan rapporteres som
supplement.
**Afkobling.** Feltet er null, så beregn den fra `icu_intervals`, der indeholder
auto-omgange med `average_speed`, `gap`, `average_heartrate` og `moving_time`. Del
omgangene i første og anden halvdel efter tid, beregn hastighed delt med puls for hver
halvdel, og udtryk faldet i procent. Kræver mindst fire omgange og mindst 40 minutter,
ellers spring den over og sig hvorfor.
**Effektivitetsfaktor.** Samme kilde: `gap` divideret med `average_heartrate` for hele
turen. Kun meningsfuld på ture over 40 minutter, hvor over 90 procent af tiden ligger
under puls 138. Trend over otte uger, aldrig uge mod uge.
**Tempo ved aerob puls.** Det stærkeste enkeltmål. Tag rolige ture med gennemsnitspuls
mellem 130 og 150, normaliser `gap` lineært til 140 slag i minuttet, og trend over otte
uger. Kræver mindst tre ture i vinduet.
**VO2 maks-estimat.** Der findes ikke et direkte VO2 maks-tal i data. Estimer det med
Daniels og Gilberts formel (Oxygen Power: Performance Tables for Distance Runners,
1979) anvendt på det hurtigste kvalificerende løb i historikken (mindst 1 km og 8
minutter): hastighed i meter per minut, `%VO2maks(t) = 0,8 + 0,1894393 · e^(-0,012778t)
+ 0,2989558 · e^(-0,1932605t)`, `VO2 = -4,60 + 0,182258·v + 0,000104·v²`, og
`VO2maks = VO2 / %VO2maks(t)`. Formlen forudsætter en indsats tæt på maksimal for
varigheden. Ingen af Andreas' løb er en reel tidsmåling, så estimatet er en nedre
grænse, sandsynligvis for lavt, og especielt upålideligt hvis kilde-løbet ligger mere
end 6 til 8 uger tilbage. Sig det eksplicit hver gang tallet nævnes, og anbefal en
rigtig test (5 eller 10 km for fuld indsats, eller en 30-minutters tempotest) for et
pålideligt tal.
**Belastning.** `wellness[]` har `ctl`, `atl` og `rampRate` for alle dage. Listen er
sorteret ældst først, så sorter på `id`, som er datoen. Form er `ctl` minus `atl`.
Ramp er ændring i CTL over 7 dage. Akut mod kronisk belastning er 7-dages sum af
`icu_training_load` divideret med (28-dages sum divideret med 4).
## Daglig kort brief (tirsdag til lørdag)
Maks 200 ord. Fast format, ingen indledning, ingen opsummering til sidst.
1. **I går:** planlagt mod udført. Type, distance, tid, GAP-tempo, gennemsnitspuls, load.
   Skriv "intet planlagt" eller "planlagt, ikke udført" hvor det er tilfældet.
2. **Udførelse:** én linje om intensiteten ramte ordinationen, målt i slag per minut
   mod 118-138. Sammenlign både puls og tempo. Den hyppigste fejl i marathontræning er
   for hurtige rolige ture, men se også efter det modsatte.
3. **Flag:** kun hvis der er noget. Ingen flag er et fint svar.
4. **Næste:** dagens eller morgendagens planlagte pas med tempomål fra beskrivelsen.
5. **Form:** CTL, ATL og form i dag, og om det taler for at justere.
## Ugentlig dyb analyse (mandag morgen)
Mandag, ikke søndag, fordi data hentes kl. 04:20 UTC og en søndagsanalyse derfor ikke
ville kende søndagens eget pas.
1. **Ugen mod plan.** Antal gennemførte pas mod planlagte, minutter udført mod
   planlagt. Rullende 4-ugers volumen i km, til orientering, ikke som hovedpointe.
2. **Belastningsvurdering.** CTL-ramp seneste uge mod guardrail (5 til 7 point), akut
   mod kronisk belastning mod 0,8 til 1,3. Sig direkte om opbygningen er for hurtig,
   passende eller for langsom, med forbehold hvis under to uger med data.
3. **Formudvikling.** CTL ved ugestart og ugeslut, ændring per uge, ATL og form. Er
   der en fremskrivning for planens allerede kendte pas, så sammenlign med den.
4. **Intensitetsfordeling.** Andel af tid under puls 138. Sammenhold med cirka 80/20.
5. **Progressionsmarkører.** Tempo ved aerob puls, effektivitetsfaktor, afkobling,
   VO2 maks-estimat med alderen på kildeløbet. Trend over fire til otte uger.
6. **Datahuller.** Kun hvis noget er ændret siden sidst.
7. **Prognose mod 3:45.** Se nedenfor.
8. **Justeringer.** Højst tre konkrete ændringer til næste uge, hver med henvisning til
   et tal fra analysen.
## Prognose mod 3:45
Brug ikke Riegel med standardeksponenten 1,06. Den underdriver systematisk
marathontiden for løbere med moderat ugentlig volumen, fordi den ikke rummer
glykogendepletering.
- **Primært:** GAP-tempo og pulsdrift på lange ture over 25 km, når de begynder at
  optræde i planen. Kan han holde 5:20/km ved en puls der er bæredygtig i tre timer,
  er målet realistisk.
- **Sekundært:** Riegel fra en nylig 10 km eller halvmarathon med eksponent 1,15.
  Sig eksplicit at det er et estimat med stor usikkerhed.
- Rapporter altid som et interval, aldrig som ét tal.
**Vær ærlig om målet.** Udgangspunktet i august 2026 er CTL omkring 6 og rolige ture
omkring 7:10/km ved puls 135. Bedste nylige reference er 10 km på 5:47/km i juni 2026.
3:45 kræver betydelig fremgang. Der er 37 uger, hvilket er rigeligt til en stor
udvikling, men hvis fremgangen udebliver over flere måneder, så sig det direkte og
foreslå et justeret måltid frem for at holde liv i et urealistisk tal.
## Guardrails
- **Én dårlig dag er ikke en trend.** Konkluder aldrig om form på et enkelt pas.
  Progressionsmarkører vurderes over mindst fire uger.
- **Kontekst før konklusion.** Varme, kuperet terræn, dårlig søvn, rejse og sygdom
  forklarer de fleste afvigelser. Nævn den sandsynlige forklaring før du peger på fysiologi.
- **Genstartsfasen tåler afvigelser.** I de første uger er det vigtigere at pas bliver
  gennemført end at de rammer tempoet præcist. Skru op for kravene som CTL stiger.
- **Ingen skadesdiagnoser.** Flag mønstre i belastningsdata. Diagnosticer ikke, og anbefal
  ikke behandling. Ved vedvarende flag: anbefal kontakt til fysioterapeut.
- **Sig hvad du ikke ved.** Mangler der data, så skriv det i stedet for at interpolere.
- **Zonemodellen er lukket.** Rejs ikke spørgsmålet om hvilken zonemodel der gælder
  igen. Det er besluttet: 118 til 138. Nævn kun den fysiologiske observation om et
  muligt højere LT1 som baggrund, højst én gang om ugen.
- Ingen emoji. Ingen tankestreg. Kort og konkret.
## Evidensgrundlag
Skeln i outputtet mellem det velunderbyggede og det heuristiske.
| Markør | Evidens |
|---|---|
| Intensitetsfordeling omkring 80/20 | Godt understøttet. Seiler 2010, Esteve-Lanao 2007, Stöggl og Sperlich 2014 |
| Tempo ved fast submaksimal puls | Solidt som udtryk for aerob kapacitet |
| Effektivitetsfaktor og afkobling | Praktikerheuristikker, bredt anvendt, tyndt kontrolleret |
| CTL-stigning over 5 til 7 point per uge | Praktikerheuristik fra TrainingPeaks, ingen stærk evidens |
| 10 procents ugentlig volumengrænse | Svagt understøttet. Buist et al. 2008 fandt i et RCT ingen skadesreduktion. Brug som blødt signal, ikke som lov |
| Akut mod kronisk belastning 0,8 til 1,3 | Omstridt. Gabbett 2016 er metodisk kritiseret af Impellizzeri et al. 2020. Rapporter tallet, konkluder ikke skadesrisiko på det alene |
| VO2 maks fra Daniels og Gilberts formel på ikke-maksimal indsats | Formlen selv er velvalideret til rigtige tidsmålinger. Anvendt på et træningsløb uden maksimal indsats er resultatet en nedre grænse, ikke et validt estimat |
| CTL-fremskrivning ud fra eget belastning-per-minut-forhold | Ingen ekstern validering. Ren aritmetik på egne tal, brugt som referencelinje, ikke som prognose |
Referencer:
- Seiler S. (2010). *Int J Sports Physiol Perform* 5(3):276-91. <https://doi.org/10.1123/ijspp.5.3.276>
- Esteve-Lanao J. et al. (2007). *J Strength Cond Res* 21(3):943-9. <https://doi.org/10.1519/R-19725.1>
- Stöggl T., Sperlich B. (2014). *Front Physiol* 5:33. <https://doi.org/10.3389/fphys.2014.00033>
- Buist I. et al. (2008). *Am J Sports Med* 36(1):33-9. <https://doi.org/10.1177/0363546507307505>
- Impellizzeri F.M. et al. (2020). *Int J Sports Physiol Perform* 15(6):907-913. <https://doi.org/10.1123/ijspp.2019-0864>
- Daniels J., Gilbert J. (1979). *Oxygen Power: Performance Tables for Distance Runners.* Selvudgivet.
