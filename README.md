# Anvero

Anvero to rozwijany lokalnie system wspierający obsługę sprzedaży z marketplace'ów. Pierwsza wersja skupia się na jednym, spójnym widoku zamówień oraz przygotowaniu architektury pod integracje Allegro i ERLI.

## Status

Sprint 1 jest zakończony: repozytorium ma ustaloną strukturę, dokumentację startową oraz skrypty do przygotowania i sprawdzenia środowiska. Implementacja aplikacji rozpocznie się w Sprincie 2.

## Szybki start (Windows)

W PowerShell, z katalogu projektu, uruchom:

```powershell
.\scripts\bootstrap.ps1
.\scripts\doctor.ps1
```

`bootstrap` tworzy lokalne środowisko Pythona i instaluje zależności, jeżeli plik z zależnościami został już dodany. `doctor` sprawdza, czy środowisko jest gotowe do dalszej pracy.

Jeżeli PowerShell blokuje uruchomienie lokalnego skryptu, użyj jednorazowo:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Dokumentacja

- [Kontekst projektu](docs/PROJECT_CONTEXT.md)
- [MVP](docs/MVP.md)
- [Architektura](docs/ARCHITECTURE.md)
- [Model danych](docs/DATABASE.md)
- [Kontrakt API](docs/API.md)
- [Plan rozwoju](docs/ROADMAP.md)
- [Rejestr decyzji](docs/DECISIONS.md)
- [Praca lokalna](docs/DEVELOPMENT.md)

## Struktura

```text
backend/    przyszła aplikacja Python i testy
frontend/   przyszły interfejs użytkownika
database/   migracje, schemat i dane przykładowe
docs/       ustalenia projektowe
scripts/    narzędzia dla lokalnego środowiska
branding/   materiały marki
```
