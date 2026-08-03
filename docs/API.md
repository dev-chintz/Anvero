# Kontrakt API

API będzie wersjonowane pod prefiksem `/api/v1`. Format komunikacji: JSON; daty: ISO 8601 w UTC.

## Planowane endpointy MVP

| Metoda | Ścieżka | Znaczenie |
| --- | --- | --- |
| `GET` | `/api/v1/health` | stan usługi |
| `GET` | `/api/v1/orders` | lista zamówień z filtrami |
| `GET` | `/api/v1/orders/{id}` | szczegóły zamówienia |
| `PATCH` | `/api/v1/orders/{id}/status` | zmiana wewnętrznego statusu |
| `GET` | `/api/v1/integrations` | lista podłączonych źródeł |

## Konwencje

- Identyfikatory API są nieprzezroczystymi identyfikatorami Anvero.
- Błędy mają format `{"detail": "czytelny opis"}` oraz właściwy kod HTTP.
- Operacje zmieniające dane wymagają uwierzytelnienia, gdy mechanizm logowania zostanie wdrożony.
- Zmiana statusu tworzy wpis w historii statusów.
