# Rejestr decyzji

## 2026-08-02 — Modularny monolit na start

**Decyzja:** budujemy pojedynczą aplikację z wyraźnymi modułami, zamiast mikroserwisów.

**Uzasadnienie:** pierwsza wersja ma być łatwa do uruchomienia i rozwijania przez mały zespół. Granice modułów zachowują możliwość późniejszego wydzielenia komponentów.

## 2026-08-02 — PostgreSQL jako docelowa baza

**Decyzja:** model danych projektujemy pod PostgreSQL.

**Uzasadnienie:** nadaje się do relacyjnych danych zamówień, zapewnia niezawodność i zostawia przestrzeń na rozwój.

## 2026-08-02 — Integracje jako adaptery

**Decyzja:** Allegro i ERLI mają osobne moduły, zwracające wspólny format domenowy.

**Uzasadnienie:** ogranicza zależność reszty systemu od szczegółów zewnętrznych API.

## 2026-08-02 — Bez Dockera w Sprincie 1

**Decyzja:** środowisko lokalne uruchamiamy natywnie.

**Uzasadnienie:** redukuje próg wejścia; kontenery zostaną dodane, gdy będą realnie potrzebne.
