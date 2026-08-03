# Model danych

Model zostanie wdrożony przez migracje po wyborze frameworka, ale już teraz obowiązuje wspólny język danych.

| Encja | Rola | Najważniejsze pola |
| --- | --- | --- |
| `integration` | skonfigurowane źródło danych | `provider`, `external_account_id`, `status` |
| `order` | zamówienie w Anvero | `id`, `integration_id`, `external_id`, `status`, `ordered_at`, `currency` |
| `order_item` | pozycja zamówienia | `order_id`, `sku`, `name`, `quantity`, `unit_price` |
| `customer` | kupujący | `name`, `email`, `phone` |
| `address` | adres dostawy lub faktury | `order_id`, `type`, dane adresowe |
| `shipment` | wysyłka | `order_id`, `carrier`, `tracking_number`, `status` |
| `order_status_history` | audyt statusów | `order_id`, `from_status`, `to_status`, `changed_at` |

`external_id` jest unikalne tylko w obrębie integracji. Kwoty przechowujemy jako wartości dziesiętne, nigdy jako `float`. Dane dostępowe do integracji nie trafiają do repozytorium ani logów.
