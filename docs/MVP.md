# MVP

## Cel

MVP ma potwierdzić, że Anvero porządkuje codzienną obsługę zamówień lepiej niż ręczne przełączanie się między marketplace'ami.

## Zakres

1. Logowanie lokalnego użytkownika.
2. Jednolista zamówień z filtrowaniem po źródle, statusie i dacie.
3. Widok szczegółów zamówienia z pozycjami, klientem, dostawą i płatnością.
4. Wewnętrzne statusy zamówienia i historia ich zmian.
5. Ręczne dodanie danych przykładowych oraz import z pierwszego źródła.
6. Adapter integracji Allegro przygotowany tak, aby nie mieszać jego logiki z resztą aplikacji.

## Poza zakresem

- obsługa wielu firm i rozliczeń abonamentowych,
- automatyczne wystawianie faktur,
- pełna obsługa kurierów i etykiet,
- synchronizacja stanów magazynowych,
- integracja ERLI przed zweryfikowaniem przepływu na pierwszym źródle,
- wdrożenie produkcyjne i Docker.

## Kryterium gotowości

Użytkownik może przejrzeć przykładowe lub pobrane zamówienie, znaleźć je filtrem, zobaczyć szczegóły i bezpiecznie zmienić jego wewnętrzny status.
