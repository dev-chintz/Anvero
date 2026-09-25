# Anvero: podsumowanie do rozmowy

Stan na 25 września 2026. Tekst napisany do słuchania i rozmowy, na przykład
w samochodzie, dlatego bez tabel i bez kodu. Szczegóły są w pozostałych
plikach w folderze docs.

## Czym jest Anvero

Anvero to nasz własny panel do obsługi sprzedaży: jedno miejsce zamiast
kilku zakładek z Allegro, Erli i InPost. Zamówienia z obu kanałów
spływają same, widać, co trzeba zrobić, co wysłać i co jest spóźnione.
Pomysł nie polega na kopiowaniu BaseLinkera. Budujemy tylko to, czego
naprawdę potrzebujemy przy 10–50 zamówieniach dziennie i towarze robionym
głównie na zamówienie. Wzorem są ekrany AlleIntegratora.

Technicznie: backend w Pythonie (FastAPI), frontend w React, baza
PostgreSQL na naszym NAS-ie z codzienną kopią na zaszyfrowany Dysk Google.
Pracujemy z kilku komputerów, z Claude i z Kiro. Cała wiedza jest w
dokumentacji w repozytorium, a nie w historii czatów.

## Co już działa naprawdę

- Logowanie. Każda strona wymaga zalogowania.
- Import zamówień z Allegro, sprawdzony na prawdziwym API w środowisku
  testowym (Sandbox).
- Lista zamówień z filtrami i szerokim wyszukiwaniem: po loginie, telefonie,
  produkcie, mieście, numerze paczki.
- Kolejki pracy: do zrobienia, nieopłacone, do wysłania, spóźnione.
  Posortowane według terminu wysyłki.
- Lista „do zrobienia”, pogrupowana po dniach i po produktach, z
  odhaczaniem. Pod towar robiony na zamówienie to lepsze niż zwykła lista
  kompletacji.
- Strona zamówienia w układzie jak w BaseLinkerze: produkty, kupujący,
  dostawa, płatność, opłaty Allegro, notatka wewnętrzna i inne zamówienia
  tego samego klienta.
- Tryb bezpieczny. Dopóki jest włączony, nic nie wychodzi do Allegro ani do
  kuriera, tylko się zapisuje, co by wyszło. Chroni przed wydaniem
  pieniędzy przez pomyłkę.
- Strona statusu, która mówi, czy połączenia i importy działają.
- Ponad 1300 testów automatycznych.

## Co jest zbudowane, ale jeszcze ani razu nie zadziałało naprawdę

To najważniejsza rzecz do zapamiętania: **kodu jest dużo, a prawdziwych
prób mało.** Poniższe rzeczy są napisane według dokumentacji i sprawdzone
tylko na atrapach:

- Import z Erli. Czeka na klucz API.
- Wysyłanie do Allegro zmian statusu i numerów paczek.
- Etykiety przez Wysyłam z Allegro, wydruk wielu naraz, zamawianie kuriera.
- Paczkomaty przez własne konto InPost. Tę ścieżkę raczej wyłączymy, o tym
  niżej.
- Wiadomości od kupujących: wspólna skrzynka i odpowiadanie.
- Zwroty, reklamacje i dyskusje, na razie tylko do odczytu, z terminami.
- Automatyczne odświeżanie co 15 minut.
- Uruchomienie na NAS-ie. Wszystko przygotowane, ale jeszcze nie odpalone.
- Produkcyjne Allegro, czyli nasze prawdziwe konto sprzedawcy. Na razie
  pracujemy tylko na Sandboxie.

## Wnioski z dzisiejszej analizy wysyłek

- **Allegro:** wszystkie przesyłki, także paczkomaty InPost, najlepiej robić
  przez Wysyłam z Allegro. Wystarczy wpisać token z Managera Paczek w
  ustawieniach Allegro. Wtedy Smart dalej rozlicza Allegro, a nie nasze
  saldo w InPost.
- **Ryzyko:** gotowa już bezpośrednia integracja z InPost przy zamówieniach
  Smart prawdopodobnie płaciłaby z naszego salda. Na szczęście tryb
  bezpieczny nic nie puścił.
- **Erli:** ma własne API do paczek i etykiet, na tym samym kluczu co import.
  Nie trzeba do tego InPosta.
- **Drukarka:** Xprinter jest w tej samej sieci co NAS, więc Anvero może
  drukować etykiety prosto na nią, bez okna drukowania. Domyślny rozmiar
  paczki to gabaryt A. Kuriera nie zamawiamy, paczki zanosimy sami.

## Największe ryzyka i słabe punkty

1. **Dużo niesprawdzonych funkcji naraz.** Jeśli przy pierwszym prawdziwym
   uruchomieniu coś nie zadziała, trudno będzie ustalić co. Lepiej odpalać
   funkcje po jednej.
2. **Brak wdrożenia na NAS.** Bez tego nic nie chodzi samo. Program działa
   tylko wtedy, gdy któryś komputer ma włączony serwer.
3. **Jedno konto Allegro i jedna osoba.** Jeśli dojdzie drugie konto albo
   pracownik, trzeba będzie dobudować role i historię zmian.
4. **Rozrost zakresu.** Kusi, żeby dorabiać kolejne funkcje z
   AlleIntegratora, zamiast najpierw odpalić to, co już jest.

## Potencjalne ulepszenia i rozwiązania

### Żeby w ogóle ruszyć

- **Jeden „dzień prób” na Sandboxie** z wyłączonym trybem bezpiecznym, według
  listy: zmiana statusu, numer paczki, jedna etykieta InPost, jedna One lub
  Orlen, odpowiedź na wiadomość, odczyt zwrotów. Po każdym punkcie
  notatka, co zadziałało.
- **Wdrożenie na NAS** zaraz potem, żeby import i odświeżanie chodziły same
  przez całą dobę.
- **Przejście na produkcyjne Allegro**, najpierw z włączonym trybem
  bezpiecznym, żeby przez kilka dni tylko czytać prawdziwe zamówienia.

### Wysyłka i pakowanie

- **„Utwórz i drukuj” jednym kliknięciem** dla wszystkich zaznaczonych
  zamówień z Allegro i Erli, z wydrukiem prosto na Xprinter.
- **Kartka do paczki:** razem z etykietą drukuje się mała lista produktów z
  numerem zamówienia, żeby przy pakowaniu nic się nie pomyliło.
- **Skanuj i drukuj:** czytnik kodów kreskowych na stanowisku. Skanujesz
  kartkę zamówienia, a Anvero drukuje etykietę i oznacza paczkę jako
  spakowaną.
- **Gabaryt i waga przypisane do produktu,** żeby etykieta sama miała dobry
  rozmiar.
- **Łączenie zamówień** tego samego kupującego w jedną paczkę.

### Produkcja na zamówienie

- **Czas wykonania przypisany do produktu.** Anvero samo ostrzega, gdy
  zamówienie nie zdąży przed terminem wysyłki.
- **Uwagi kupującego na liście do zrobienia,** na przykład personalizacja
  albo kolor z wiadomości, żeby nie trzeba było ich szukać.
- **Widok na telefon** do pracowni: lista na dziś z odhaczaniem, bez
  siadania do komputera.

### Klienci i wiadomości

- **Szablony odpowiedzi** na typowe pytania: kiedy wysyłka, gdzie paczka,
  jak zwrócić.
- **Szkice odpowiedzi pisane przez AI,** na przykład przez Claude, do
  zatwierdzenia jednym kliknięciem. Szkic od razu zawiera numer paczki i
  status zamówienia.
- **Alarm, gdy wiadomość czeka za długo,** bo Allegro patrzy na czas
  odpowiedzi.

### Zwroty i reklamacje

- **Akcje prosto z Anvero:** przyjęcie, odrzucenie, odpowiedź. Wszystko
  przez tryb bezpieczny.
- **Automatyczny wniosek o zwrot prowizji** z Allegro po zwrocie. To
  odzyskane pieniądze, o które łatwo zapomnieć.

### Pieniądze i faktury

- **Wybór programu do faktur** (do porównania: Fakturownia, inFakt, wFirma),
  z obsługą KSeF, który jest już obowiązkowy.
- **Faktura wystawiana automatycznie** po wysyłce i wgrywana do Allegro.
- **Ile zostaje na zamówieniu:** cena minus prowizje Allegro, minus koszt
  materiałów. Prowizje już są czytane, brakuje tylko kosztu produktu.
- **Podsumowanie miesiąca:** sprzedaż, opłaty, najlepsze produkty.

### Spokój ducha

- **Powiadomienia na telefon,** na przykład Telegram albo e-mail, gdy:
  - import się nie udał,
  - kończy się połączenie z Allegro,
  - mija termin reklamacji.
- **Tygodniowy raport** na maila: ile zamówień, ile spóźnionych, co czeka.

### Dalsza przyszłość

- Kolejne kanały sprzedaży, jeśli zaczniemy tam sprzedawać.
- Reguły typu „jeśli coś, to zrób coś”, na przykład automatyczny status po
  wydruku.
- Kiedyś może produkt dla innych sprzedawców. Na razie to tylko pomysł.
  Najpierw ma służyć nam.

## Pytania do przegadania

1. **Kolejność:** najpierw dzień prób i NAS, czy najpierw druk etykiet, bo
   to najbardziej odczuwalne na co dzień?
2. **Model Xprintera i rozmiar etykiet.** Czy etykieta ma zmieniać status na
   „wysłane”, czy robimy to ręcznie?
3. **Czy token ShipX jest już wpisany w ustawieniach Wysyłam z Allegro?** Czy
   paczka InPost bez Smart idzie z salda InPost, czy na fakturę Allegro?
4. **Czy w Erli mamy Erli Pro?**
5. **Który program do faktur?** Czy faktury mają się wystawiać same?
6. **Czy ktoś poza Tobą będzie używał Anvero?** Czy dojdzie drugie konto
   Allegro?
7. **Które z ulepszeń wyżej dałoby najwięcej oszczędności czasu każdego
   dnia?** Wybierzmy trzy.

## Proponowany plan na najbliższe tygodnie

1. Dzień prób na Sandboxie, po jednej funkcji naraz.
2. Uruchomienie na NAS-ie.
3. Druk na Xprinterze i etykiety przez Wysyłam z Allegro.
4. Produkcyjne Allegro, najpierw tylko czytanie.
5. Klucz Erli: import, potem paczki z Erli.
6. Dopiero potem nowe funkcje, według trzech wybranych ulepszeń.
