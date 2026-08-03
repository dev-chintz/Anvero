# Praca lokalna

## Wymagania

- Windows PowerShell 5.1 lub PowerShell 7,
- Git,
- Python 3.11 lub nowszy,
- Node.js 20 lub nowszy — wymagany dopiero wraz z frontendem,
- PostgreSQL 16 lub nowszy — wymagany od Sprintu 2.

## Przygotowanie

1. Otwórz PowerShell w katalogu głównym projektu.
2. Uruchom `./scripts/bootstrap.ps1`.
3. Uruchom `./scripts/doctor.ps1` i usuń zgłoszone błędy.

Skrypty nie instalują Pythona, Node.js, Gita ani PostgreSQL i nie modyfikują globalnej konfiguracji komputera. `bootstrap` może bezpiecznie uruchamiać się wielokrotnie.

## Zależności backendu

Gdy pojawi się `backend/requirements/base.txt`, bootstrap zainstaluje go do `.venv`. Do ręcznej aktywacji środowiska użyj:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Kontrola jakości

Przed przekazaniem zmian uruchamiaj `./scripts/doctor.ps1`. W Sprintach implementacyjnych dokument zostanie rozszerzony o polecenia testów i formatowania.
