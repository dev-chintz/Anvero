# Architektura

## Zasada

Anvero jest podzielone na frontend, backend i bazę danych. Integracje z marketplace'ami są adapterami: tłumaczą dane konkretnej platformy na wspólny model Anvero.

```text
Frontend -> API backendu -> usługi domenowe -> PostgreSQL
                              ^
                              |
                    adaptery Allegro / ERLI
```

## Odpowiedzialności

- `frontend/` — widoki, formularze, komunikacja z API.
- `backend/app/api/` — endpointy HTTP i walidacja wejścia.
- `backend/app/services/` — przypadki użycia oraz reguły biznesowe.
- `backend/app/integrations/` — klient i mapowanie danych każdego zewnętrznego API.
- `backend/app/models/` — modele trwałych danych.
- `backend/app/schemas/` — kontrakty danych API.
- `database/` — migracje, definicje schematu i dane demonstracyjne.

## Założenia Sprintu 1

Python będzie językiem backendu, PostgreSQL docelową bazą, a interfejs będzie aplikacją webową. Wybór frameworków nastąpi przed implementacją Sprintu 2 i zostanie zapisany w `DECISIONS.md`.

## Granice

Frontend nie komunikuje się bezpośrednio z bazą ani API marketplace'ów. Kod Allegro i ERLI nie przekazuje swoich surowych struktur poza moduł integracji.
