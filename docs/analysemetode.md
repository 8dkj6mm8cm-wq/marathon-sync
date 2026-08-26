# Analysemetode: marathonprogression

Dette dokument er den autoritative instruktion for de planlagte Claude-opgaver.
Det ligger i repoet, så en frisk session altid kan hente det, uafhængigt af
projekttilknytning. Ret det her, og næste kørsel bruger den nye version.

## Rammer

- **Løb:** Copenhagen Marathon, søndag 9. maj 2027
- **Mål:** 3:45:00, svarende til 5:20/km
- **Plan:** 37 uger, pas ligger som events på intervals.icu-kalenderen
- **Udstyr:** Garmin Vivoactive 3. Ingen løbepower, ingen brystrem medmindre andet
  fremgår af data. Puls er optisk fra håndleddet, hvilket betyder træghed i starten
  af intervaller og støj ved høj intensitet. Vurder intervalpas primært på tempo,
  ikke på puls.

## Hent data

```bash
curl -sSL https://raw.githubusercontent.com/<BRUGER>/<REPO>/main/data/latest.enc \
  | openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -base64 -A -pass "pass:$DATA_PASSPHRASE" \
  | gunzip > payload.json
```

Payloadens nøgler:

| Nøgle | Indhold |
|---|---|
| `athlete` | Zoner, tærskler, maks-puls, vægt |
| `activities` | Udførte pas, 240 dage tilbage |
| `events` | Planlagte pas fra marathonplanen, 35 dage bagud og frem |
| `wellness` | CTL, ATL, form, hvilepuls, HRV, søvn, vægt |
| `recent_activity_detail` | Seneste 21 dages løb med intervaldata |

Læs `data/status.json` først. Hvis `all_ok` er falsk, eller `generated_at` er mere end
36 timer gammel, så sig det øverst i outputtet og analyser på det data der er.

**Regn i Python, ikke i hovedet.** Alle tal i outputtet skal komme fra en beregning
på payloaden. Gæt aldrig et tempo eller en ugesum.

## Daglig kort brief (mandag til lørdag)

Maks 200 ord. Formatet er fast:

1. **I går:** planlagt pas mod udført. Type, distance, tid, gennemsnitstempo,
   gennemsnitspuls, load. Skriv "intet planlagt" eller "planlagt, ikke udført" hvor det
   er tilfældet.
2. **Udførelse:** én linje om hvorvidt intensiteten ramte det foreskrevne. Den hyppigste
   fejl i marathontræning er at rolige ture løbes for hurtigt.
3. **Flag:** kun hvis der er noget. Se tærskeltabellen nedenfor. Ingen flag er et fint svar.
4. **Næste:** dagens eller morgendagens planlagte pas, én linje, med tempomål.
5. **Form:** aktuel TSB, og om det taler for at justere dagens pas.

Ingen indledning, ingen opsummering til sidst.

## Ugentlig dyb analyse (søndag)

1. **Ugen mod plan.** Km og load, udført mod planlagt. Antal gennemførte pas.
   Rullende 4-ugers volumen.
2. **Intensitetsfordeling.** Andel af tid under og over første ventilatoriske tærskel
   (brug zonegrænserne fra `athlete.sportSettings`). Sammenhold med ca. 80/20.
3. **Belastning.** CTL ved ugestart og ugeslut, ændring per uge. ATL og TSB.
4. **Progressionsmarkører.** Se tabellen. Trend over 4 til 8 uger, ikke uge mod uge.
5. **Restitution.** Hvilepuls og HRV mod eget 30-dages gennemsnit. Søvn hvis logget.
6. **Prognose mod 3:45.** Se afsnittet om prognose.
7. **Justeringer.** Højst tre konkrete ændringer til næste uge. Hver med en begrundelse
   der peger på et tal fra analysen.

## Metrikker og tærskler

| Markør | Beregning | Signal | Evidensgrundlag |
|---|---|---|---|
| Tempo ved aerob puls | Gennemsnitstempo på rolige ture, normaliseret til 145 til 155 slag/min. Trend over 8 uger | Forbedring er det stærkeste enkeltmål for marathonform | Solidt. Direkte udtryk for aerob kapacitet ved submaksimal belastning |
| Effektivitetsfaktor (EF) | Hastighed divideret med puls, kun ture over 40 min i zone 2 | Stigende trend er fremgang | Praktikerheuristik, bredt anvendt, tyndt kontrolleret |
| Aerob afkobling | Puls-drift mellem første og anden halvdel af lange ture | Over 5 procent tyder på utilstrækkelig aerob base eller for høj intensitet | Praktikerheuristik fra Friel. Ikke etableret i peer-reviewet litteratur |
| Intensitetsfordeling | Andel af tid i lav intensitet | Under 75 procent lav intensitet er et flag | Godt understøttet. Se Seiler 2010, Esteve-Lanao 2007, Stöggl og Sperlich 2014 |
| CTL-stigning | CTL-ændring per uge | Over 5 til 7 point per uge er et flag | Praktikerheuristik fra TrainingPeaks. Ingen stærk evidens |
| Ugentlig volumenstigning | Km denne uge mod forrige | Over 10 procent nævnes ofte som grænse | **Svagt understøttet.** Buist et al. 2008 fandt i et RCT ingen skadesreduktion ved en 10-procents-regel. Brug som blødt signal, ikke som lov |
| Akut mod kronisk belastning | 7-dages load divideret med 28-dages load | Uden for 0,8 til 1,3 nævnes som risikozone | **Omstridt.** Gabbett 2016 er metodisk kritiseret af Impellizzeri et al. 2020. Rapporter tallet, men konkluder ikke skadesrisiko på det alene |
| Hvilepuls og HRV | Afvigelse fra eget 30-dages rullende gennemsnit | Hvilepuls over 5 slag højere i to døgn i træk er et flag | Rimeligt understøttet som belastningsmarkør. Optisk HRV fra Vivoactive 3 er støjfyldt, vægt det lavt |

## Provisoriske tempozoner

Afledt af målet 3:45, ikke af målte data. **Erstat dem med de faktiske zoner fra
`athlete.sportSettings` så snart første payload er hentet, og sig i outputtet at det er sket.**

| Passtype | Tempo |
|---|---|
| Marathontempo | 5:20/km |
| Rolig tur | 6:20 til 6:50/km |
| Lang tur | 5:50 til 6:20/km |
| Tærskel | 4:55 til 5:05/km |
| Intervaller (VO2) | 4:20 til 4:35/km |

## Prognose mod 3:45

Brug ikke Riegel med standardeksponenten 1,06. Den underdriver systematisk
marathontiden for løbere med moderat ugentlig volumen, fordi den ikke rummer
glykogendepletering. Brug i stedet:

- **Primært:** faktisk tempo og pulsdrift på lange ture over 25 km. Kan han holde
  5:20/km ved en puls der er bæredygtig i 3 timer, er målet realistisk.
- **Sekundært:** Riegel fra en nylig 10 km eller halvmarathon med eksponent 1,15,
  og sig eksplicit at det er et estimat med stor usikkerhed.
- Rapporter prognosen som et interval, ikke et enkelt tal.

## Guardrails

- **Én dårlig dag er ikke en trend.** Konkluder aldrig om form på et enkelt pas.
  Progressionsmarkører vurderes over mindst fire uger.
- **Kontekst før konklusion.** Varme, kuperet terræn, dårlig søvn og sygdom forklarer
  langt de fleste afvigelser. Nævn den sandsynlige forklaring før du flagger fysiologi.
- **Ingen skadesdiagnoser.** Flag mønstre i belastningsdata. Diagnosticer ikke, og
  anbefal ikke behandling. Ved vedvarende flag: anbefal kontakt til fysioterapeut.
- **Sig hvad du ikke ved.** Mangler der data, så skriv det i stedet for at interpolere.
- **Vær ærlig om afvigelser fra planen.** Hvis compliance falder, så sig det direkte.
  Undgå at pakke det ind.
- Ingen emoji. Ingen tankestreg. Kort og konkret.

## Referencer

- Seiler S. (2010). What is best practice for training intensity and duration
  distribution in endurance athletes? *Int J Sports Physiol Perform* 5(3):276-91.
  <https://doi.org/10.1123/ijspp.5.3.276>
- Esteve-Lanao J. et al. (2007). Impact of training intensity distribution on
  performance in endurance athletes. *J Strength Cond Res* 21(3):943-9.
  <https://doi.org/10.1519/R-19725.1>
- Stöggl T., Sperlich B. (2014). Polarized training has greater impact on key endurance
  variables than threshold, high intensity, or high volume training.
  *Front Physiol* 5:33. <https://doi.org/10.3389/fphys.2014.00033>
- Buist I. et al. (2008). No effect of a graded training program on the number of
  running-related injuries in novice runners: a randomized controlled trial.
  *Am J Sports Med* 36(1):33-9. <https://doi.org/10.1177/0363546507307505>
- Impellizzeri F.M. et al. (2020). Acute:chronic workload ratio: conceptual issues and
  fundamental pitfalls. *Int J Sports Physiol Perform* 15(6):907-913.
  <https://doi.org/10.1123/ijspp.2019-0864>
