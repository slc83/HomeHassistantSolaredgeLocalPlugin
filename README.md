# SolarEdge Local per Home Assistant

Integrazione personalizzata per **Home Assistant Core 2026.6.2**, pensata per
leggere un **SolarEdge SE6000H-RW000BEN4** dalla rete locale tramite Modbus TCP /
SunSpec. Non richiede API key o account cloud. Il rilevamento avviene tramite
IP/hostname inserito manualmente, senza scansione della rete.

Il codice usa le API della versione richiesta; la compatibilità sul tuo specifico
inverter deve essere verificata con il firmware installato. Non è stato possibile
provare un inverter fisico in questo ambiente. Sono supportati i modelli SunSpec
interi 101, 102 e 103; i dati disponibili dipendono dall'inverter.

Verificato in un ambiente temporaneo con **Core 2026.6.2** e inverter TCP
simulato: configurazione, caricamento di 14 sensori, prevenzione dei duplicati,
modifica opzioni con ricaricamento, indisponibilità/ripristino e scaricamento.

## Preparazione dell'inverter

1. Collega l'inverter alla stessa rete raggiungibile da Home Assistant,
   preferibilmente via Ethernet. Assegna una prenotazione DHCP nel router.
2. Nell'interfaccia di configurazione SolarEdge (SetApp / SolarEdge Go, secondo
   firmware e credenziali disponibili) abilita **Site Communication → Modbus TCP
   → Enable**. Se non puoi accedere alle impostazioni, chiedi all'installatore.
3. Annota IP, porta e ID Modbus. Per i modelli senza display i valori usuali sono
   **1502** e **1**. Nei modelli con display la porta può essere **502**:
   usa sempre il valore mostrato dall'inverter.
4. Ferma altri programmi o integrazioni che interrogano lo stesso endpoint:
   SolarEdge documenta una sola connessione Modbus contemporanea.

La disponibilità via Wi-Fi varia con firmware e configurazione: la rete Wi-Fi
temporanea di configurazione non sostituisce il collegamento LAN permanente.
Non occorre aprire porte sul router verso Internet.

## Installazione

1. Estrai `dist/solaredge_local-1.0.0.zip` nella directory di configurazione di
   Home Assistant (normalmente `/config`), oppure copia manualmente la cartella
   `custom_components/solaredge_local` in `/config/custom_components/`.
2. Verifica che il manifest si trovi in
   `/config/custom_components/solaredge_local/manifest.json`.
3. Riavvia Home Assistant.
4. Apri **Impostazioni → Dispositivi e servizi → Aggiungi integrazione →
   SolarEdge Local**.
5. Inserisci IP, porta, ID Modbus e intervallo di aggiornamento (default 30 s;
   minimo 10 s). Prima di salvare viene verificata una lettura reale.

La configurazione è disponibile in italiano e inglese. Dal pulsante di
configurazione dell'integrazione puoi modificare indirizzo, porta, ID e intervallo.
Il seriale impedisce duplicati e mantiene stabili le entità al cambio di IP.

## Dati esposti

- Potenza AC, energia totale prodotta in kWh.
- Tensione e corrente AC, frequenza di rete.
- Potenza, tensione e corrente DC.
- Temperatura dissipatore, potenza apparente e reattiva, fattore di potenza.
- Stato operativo e codice stato del produttore.

Le misure non supportate risultano sconosciute; una connessione persa rende i
sensori non disponibili e viene ritentata automaticamente. Il contatore energia
usa `total_increasing` ed è selezionabile come produzione solare nella dashboard
**Energia**. Per produzione giornaliera/mensile puoi aggiungere un helper
**Contatore di utenza** usando l'energia totale come sorgente. Il valore zero
dell'accumulatore SunSpec indica dato non implementato e viene esposto come
sconosciuto, evitando falsi azzeramenti nelle statistiche.

Questa versione legge esclusivamente l'inverter: non include batterie, contatori
esterni, consumi domestici, import/export o dati dei singoli ottimizzatori.
Non invia comandi di scrittura all'inverter.

## Prova della connessione senza Home Assistant

Con Python 3.11 o successivo, senza dipendenze aggiuntive:

```bash
python3 tools/probe.py 192.168.1.50 --port 1502 --unit-id 1
```

Esegui la prova da un computer che raggiunge la LAN dell'inverter, fermando prima
altre letture Modbus. Stampa identità e misure in JSON. Usa l'IP reale del tuo
inverter al posto dell'esempio. Nessun indirizzo dell'impianto è preconfigurato.

Se fallisce: controlla Modbus abilitato, indirizzo, porta, ID, firewall/VLAN e
assenza di altri client. Ripeti durante il giorno se il dispositivo è
irraggiungibile di notte. Un errore di modello non supportato indica che la
risposta non corrisponde alla mappa SunSpec implementata.

## Verifiche per lo sviluppo

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q custom_components tools tests
```

Con Home Assistant Core 2026.6.2 installato nell'ambiente Python, esegui anche:

```bash
python3 tests/ha_smoke.py
```

I test verificano decodifica, segni, fattori di scala, contatore a 32 bit,
sentinelle e comunicazione TCP con un server simulato (frammentazione, timeout,
errori, cancellazione e riconnessione). Non sostituiscono una prova su Home
Assistant con l'hardware reale.

## Riferimenti

- [SolarEdge: SunSpec Implementation Technical Note](https://knowledge-center.solaredge.com/sites/kc/files/sunspec-implementation-technical-note.pdf)
- [Home Assistant: flussi di configurazione](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
- [DataUpdateCoordinator in Core 2026.6.2](https://github.com/home-assistant/core/blob/2026.6.2/homeassistant/helpers/update_coordinator.py)

La mappa usa indirizzi Modbus base zero: firma a 40000, modello inverter a 40069.
Il trasporto implementa solo la funzione 03 e chiude la connessione a ogni ciclo.
