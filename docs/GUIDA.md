# Guida utente di DualVault (italiano)

*[English version](USER_GUIDE.md)*

DualVault crea automaticamente copie di sicurezza (backup) delle tue cartelle importanti su un disco esterno e/o sul cloud, conserva più versioni nel tempo e cancella da solo quelle troppo vecchie.

> ⚠️ DualVault è fornito "così com'è", senza garanzie. Conserva sempre più di una copia dei dati importanti e **prova ogni tanto a ripristinare un backup** per essere sicuro che funzioni.

---

## 1. Come funziona (in breve)

Ogni volta che DualVault esegue un backup, per ogni cartella configurata:

1. **Crea uno snapshot**: un file ZIP con tutti i file della cartella, più un elenco con l'impronta digitale (SHA-256) di ogni file, per poter verificare in seguito che nulla sia stato danneggiato.
2. **Cifra lo snapshot** (solo se hai attivato la cifratura) con una password che scegli tu.
3. **Copia lo snapshot su ogni destinazione** (disco esterno, cartella di rete, cloud) e controlla che la copia sia identica all'originale.
4. **Applica la rotazione**: tiene le versioni più recenti e alcune giornaliere, settimanali e mensili; cancella le altre.

Il nome di ogni snapshot contiene data e ora (in UTC), per esempio:

```
E:\Backups\documenti\dualvault-documenti-20260315T020000Z.zip
```

Se una destinazione non è disponibile (disco scollegato, niente internet) viene saltata con un avviso e le altre funzionano comunque.

---

## 2. Installazione

### 2.1 Installa Python

DualVault richiede **Python 3.10 o più recente**.

- **Windows**: scarica Python da <https://www.python.org/downloads/>. Durante l'installazione **spunta "Add python.exe to PATH"**.
- **macOS**: scarica da python.org oppure `brew install python`.
- **Linux**: di solito è già presente; per la GUI potrebbe servire il pacchetto `python3-tk` (es. `sudo apt install python3-tk`).

Verifica aprendo un terminale (su Windows: *PowerShell*):

```
python --version
```

### 2.2 Installa DualVault

```
pip install git+https://github.com/makaDv/DualVault.git
```

Se `pip` non ha accesso a Git, scarica lo ZIP del progetto da GitHub (*Code → Download ZIP*), estrailo, apri un terminale nella cartella estratta e lancia:

```
pip install .
```

Verifica:

```
dualvault --version
```

> 💡 Se compare "comando non trovato", usa `python -m dualvault` al posto di `dualvault` in tutti i comandi di questa guida.

---

## 3. Primo utilizzo con l'interfaccia grafica

```
dualvault gui
```

1. **Sources** → *Add folder...* → scegli la cartella da salvare (es. Documenti) → dai un nome breve (solo lettere, numeri, `-` o `_`, es. `documenti`) → facoltativamente indica i file da escludere separati da virgola (es. `*.tmp, node_modules`).
2. **Destinations** → *Add local/external folder...* → scegli una cartella sul disco esterno (es. `E:\Backups`) → dai un nome (es. `esterno`).
3. **Settings** → imposta quante versioni tenere (vedi §6) e, se vuoi, attiva *Encrypt backups*.
4. Clicca **Save settings**.
5. Clicca **Back up now**. Nella scheda **Log** vedi l'avanzamento.

---

## 4. Primo utilizzo da riga di comando

```
dualvault init
dualvault add-source documenti "C:\Users\TuoNome\Documents" --exclude "*.tmp" --exclude "~$*"
dualvault add-dest esterno --path "E:\Backups"
dualvault run
dualvault list
```

| Comando | Cosa fa |
|---|---|
| `dualvault init` | crea la configurazione vuota |
| `dualvault add-source NOME CARTELLA` | aggiunge una cartella da salvare (`--exclude` ripetibile) |
| `dualvault add-dest NOME --path CARTELLA` | aggiunge un disco/cartella di destinazione |
| `dualvault add-dest NOME --rclone REMOTE:CARTELLA` | aggiunge una destinazione cloud |
| `dualvault remove source NOME` / `remove dest NOME` | toglie dalla configurazione (non cancella i backup) |
| `dualvault set ...` | cambia rotazione, cifratura ecc. |
| `dualvault show` | mostra configurazione e posizione dei file |
| `dualvault run` | esegue il backup adesso |
| `dualvault list` | elenca gli snapshot |
| `dualvault verify NOME --dest DEST` | controlla l'integrità di uno snapshot |
| `dualvault restore NOME --dest DEST --to CARTELLA` | ripristina |
| `dualvault prune --dry-run` | mostra cosa cancellerebbe la rotazione |
| `dualvault schedule --at HH:MM --install` | backup automatico giornaliero |
| `dualvault gui` | apre l'interfaccia grafica |

Aiuto su ogni comando: `dualvault <comando> --help`.

---

## 5. Backup sul cloud (Google Drive, OneDrive, Dropbox, S3...)

DualVault usa **rclone**, un programma gratuito che supporta oltre 70 servizi cloud. Le tue credenziali restano dentro rclone: DualVault non le vede mai.

1. Installa rclone: <https://rclone.org/install/> (su Windows: `winget install Rclone.Rclone`).
2. Configura il tuo servizio una volta sola:
   ```
   rclone config
   ```
   Scegli `n` (new remote), dai un nome (es. `gdrive`), scegli il servizio e segui le istruzioni (di solito si apre il browser per l'accesso).
3. Aggiungi la destinazione a DualVault:
   ```
   dualvault add-dest cloud --rclone "gdrive:Backups/DualVault"
   ```

> 💡 Alternativa senza rclone: se hai l'app desktop di Google Drive/OneDrive/Dropbox, puoi usare la sua cartella sincronizzata come destinazione locale (`--path`).

---

## 6. Rotazione delle versioni

```
dualvault set --keep-last 7 --keep-daily 7 --keep-weekly 4 --keep-monthly 12
```

| Impostazione | Conserva |
|---|---|
| `keep-last` | gli ultimi N snapshot |
| `keep-daily` | il più recente di ognuno degli ultimi N giorni con backup |
| `keep-weekly` | il più recente di ognuna delle ultime N settimane |
| `keep-monthly` | il più recente di ognuno degli ultimi N mesi |

Uno snapshot resta se **almeno una** regola lo sceglie. Con i valori sopra hai circa un anno di storia occupando ~30 snapshot. La rotazione lavora per ogni cartella e ogni destinazione separatamente.

Prima di cambiare le regole, controlla cosa verrebbe cancellato:

```
dualvault prune --dry-run
```

---

## 7. Cifratura

```
dualvault set --encrypt
```

Da quel momento i nuovi snapshot hanno estensione `.zip.dvenc` e sono cifrati con AES-256-GCM. Ad ogni backup manuale ti verrà chiesta la password (due volte).

> 🔑 **Se perdi la password, i backup cifrati sono irrecuperabili. Nessuno può aiutarti a recuperarli.** Conservala in un gestore di password.

Per i backup automatici (che non possono chiederti nulla) scegli uno dei due modi:

- un file con la password nella prima riga:
  ```
  dualvault set --password-file "C:\percorso\sicuro\dualvault-pw.txt"
  ```
  Proteggi il file (solo il tuo utente deve poterlo leggere) e **non metterlo sul disco di backup**;
- la variabile d'ambiente `DUALVAULT_PASSWORD`.

Per tornare ai backup non cifrati: `dualvault set --no-encrypt`.

---

## 8. Backup automatico

```
dualvault schedule --at 02:00            # mostra cosa verrebbe configurato
dualvault schedule --at 02:00 --install  # lo attiva
```

- **Windows**: crea l'attività "DualVault" in *Utilità di pianificazione*. Il PC deve essere acceso all'orario scelto.
- **Linux**: crea un timer systemd utente; se il PC era spento, il backup parte all'avvio successivo.
- **macOS**: crea un agente launchd.

Per disattivarlo: `dualvault schedule --remove --install`.

> ⚠️ Collega il disco esterno prima dell'orario del backup, altrimenti quella destinazione viene saltata (lo trovi scritto nel log).

---

## 9. Ripristinare i file

1. Guarda quali snapshot hai:
   ```
   dualvault list
   ```
2. (Facoltativo) verifica che lo snapshot sia integro:
   ```
   dualvault verify documenti --dest esterno
   ```
3. Ripristina **in una cartella nuova e vuota** (consigliato, così non sovrascrivi nulla):
   ```
   dualvault restore documenti --dest esterno --to "C:\Ripristino"
   ```
   Per una versione specifica:
   ```
   dualvault restore documenti --dest esterno --snapshot dualvault-documenti-20260315T020000Z.zip --to "C:\Ripristino"
   ```
4. Controlla i file e copiali dove ti servono.

DualVault controlla l'integrità dello snapshot prima di estrarlo. Se la cartella di destinazione non è vuota si ferma; usa `--force` solo se sai cosa stai facendo (i file con lo stesso nome vengono sovrascritti).

> 💡 Gli snapshot **non cifrati** sono normali file ZIP: puoi aprirli con qualsiasi programma, anche senza DualVault.

---

## 10. Dove sono configurazione e log

| Sistema | Configurazione | Log |
|---|---|---|
| Windows | `%APPDATA%\DualVault\config.toml` | `%LOCALAPPDATA%\DualVault\logs\dualvault.log` |
| Linux | `~/.config/dualvault/config.toml` | `~/.local/state/dualvault/logs/` |
| macOS | `~/Library/Application Support/DualVault/` | `.../DualVault/state/logs/` |

`dualvault show` mostra i percorsi esatti. La configurazione è un file di testo modificabile: vedi l'esempio [`examples/config.example.toml`](../examples/config.example.toml).

---

## 11. Problemi comuni

| Messaggio / problema | Soluzione |
|---|---|
| `dualvault: command not found` | usa `python -m dualvault ...`, oppure aggiungi la cartella *Scripts* di Python al PATH |
| `Configuration not found` | esegui prima `dualvault init` |
| `Destination ... skipped: Drive E:\ is not connected` | collega il disco e rilancia |
| `rclone not found` | installa rclone (§5) o indica il percorso con `dualvault set --rclone-binary PERCORSO` |
| `rclone remote 'xxx:' is not configured` | esegui `rclone config` e usa lo stesso nome |
| `A password is required but none is available non-interactively` | il backup automatico è cifrato ma manca la password: vedi §7 |
| `Decryption failed: wrong password or corrupted file` | password sbagliata o file danneggiato: prova un altro snapshot |
| `Another backup is running` | aspetta la fine del backup in corso |
| `Not enough free space` | libera spazio o riduci la rotazione |
| La GUI non si apre su Linux | installa `python3-tk` |

Codici di uscita di `dualvault run`: `0` tutto ok, `2` ok con avvisi (destinazione saltata o file illeggibili), `1` errore. Il dettaglio è sempre nel log.

---

## 12. Aggiornare e disinstallare

```
pip install --upgrade git+https://github.com/makaDv/DualVault.git   # aggiorna
dualvault schedule --remove --install                               # togli la pianificazione
pip uninstall dualvault                                             # disinstalla
```

La disinstallazione non cancella né i backup né la configurazione (cartelle del §10).

---

## Supporto

- Bug e richieste: [Issues](https://github.com/makaDv/DualVault/issues). Prima di incollare un log, **togli percorsi e nomi personali**.
- Problemi di sicurezza: **non** aprire una issue pubblica, vedi [SECURITY.md](../SECURITY.md).
