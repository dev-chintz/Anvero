# Anvero's brand

The logo and the brand brief the owner had drawn with Gemini (2026-09-30), kept here as the
source. `anvero-brand-board.jpg` is the board; the brief follows below as the owner received it.

## What the application takes from it

Only the logo (`DECISIONS.md`, 2026-09-30, "The logo"). The application's looks, their colours
and their type stay as `STYLE_GUIDE.md` sets them; the brief's palette (Cobalt Flow as the main
accent) and its fonts (Inter, Roboto) are not used in the interface.

- **The mark:** redrawn as a vector from the board, in `frontend/public/favicon.svg` and
  `frontend/src/components/AnveroLogo.tsx` (`AnveroLogo`). Navy `#0f172a` (`--brand-ink`) and
  mint `#3ae4c8` (`--brand-teal`), sampled from the board; on a dark page the navy turns white,
  as the board's negative version does, and the mint stays.
- **The name:** `AnveroWordmark`, "ANVERO" in Montserrat Bold, the face the board draws it in
  (the brief says Inter Bold, which is not what the board shows), in `--brand-ink`. "Sales
  Management System" under it where there is room (the login page; the menu is too narrow).
- **One favicon:** the main mark. The board also shows a round two-arrow symbol beside it; that
  is a second, different symbol, not used.

## What the board and the brief get wrong

The board is a generated image, and some of its labels do not match what it shows: "3. Full
Color Stacked" is a horizontal version, "5. Pure White (Negative)" shows the navy logo on white,
and "Inter" appears where it means nothing ("Symbol (Favicon) Inter", "8mm Brand Font"). The
brief names Cobalt Flow `#0284c7` as the main colour and Emerald `#10b981` or teal `#14b8a6` as
the second, but the logo holds no blue and its mint is neither of those. Where the board and the
brief disagree, the board (what the owner saw and approved) wins.

## The brief, as received

> SYSTEM IDENTYFIKACJI WIZUALNEJ I STRATEGIA MARKI: ANVERO
>
> Dokument specyfikacji systemowej (Master Brand Prompt) przeznaczony do transferu kontekstu
> między modelami AI.

**1. Wprowadzenie i metadane projektu**

- Nazwa marki: Anvero
- Branża i oferta: System obsługi sprzedaży z marketplace'ów (integrator / ERP e-commerce ze
  szczególnym uwzględnieniem Allegro i Erli).
- Główna grupa docelowa: Menedżerowie e-commerce, właściciele średnich firm handlowych oraz
  specjaliści operacyjni obsługujący zamówienia, zwroty i logistykę na portalach Allegro i Erli
  (od 50 do 500+ zamówień dziennie).
- Status projektu: Pełna identyfikacja wizualna, strategia oraz specyfikacja techniczna logo
  zatwierdzone do wdrożenia.

**2. Analiza odbiorców i otoczenia rynkowego**

2.1. Profil odbiorcy: Odbiorcy to praktycy e-commerce, którzy spędzają w systemach
sprzedażowych wiele godzin dziennie. Są pod presją czasu, terminów wysyłek oraz wskaźników
jakości obsługi na Allegro i Erli. Nie szukają „efektownych wodotrysków", lecz maksymalnej
niezawodności, szybkości działania i eliminacji błędów ludzkich.

2.2. Otoczenie konkurencyjne (hipoteza rynkowa): Wobec dominacji graczy takich jak BaseLinker
czy Apilo, którzy stawiają na masowość i rozbudowane menu najeżone technicznym żargonem, Anvero
pozycjonuje się jako rozwiązanie skoncentrowane na chirurgicznej precyzji, ergonomii oraz
natywnym, równorzędnym wsparciu polskiego rynku marketplace (w tym dynamicznie rosnącego Erli
obok Allegro).

2.3. Wnioski strategiczne (potrzeba → konsekwencja):

1. Potrzeba natychmiastowej weryfikacji statusu zamówienia/zwrotu → wysokokontrastowy interfejs
   i czysta hierarchia informacji wizualnej, zapobiegająca zmęczeniu wzroku.
2. Obawa przed awarią lub opóźnieniem synchronizacji w szczycie sprzedaży → wykorzystanie
   solidnych, statecznych kolorów (granat) połączonych z energią wzrostu (turkus/szmaragd).
3. Kryterium szybkiego wdrożenia zespołu bez wielotygodniowych szkoleń → minimalistyczny,
   intuicyjny język wizualny oparty na powtarzalnych modułach i siatce 8px.
4. Wielokanałowość (Allegro + Erli) → symbolika łącząca dwa strumienie danych w jeden spójny
   proces w logotypie i ikonie.
5. Potrzeba profesjonalnego wizerunku w oczach klientów końcowych (b2b2c) → dopracowana,
   nowoczesna typografia i eleganckie materiały dokumentowe (faktury, etykiety).

**3. Fundament marki**

- Pozycjonowanie i obietnica: „Anvero to inteligentny nerwowy węzeł Twojej sprzedaży na
  marketplace'ach — zmienia chaos zamówień z Allegro i Erli w uporządkowany, zautomatyzowany
  przepływ." Gwarancja oszczędności czasu i całkowitej kontroli nad operacjami.
- Główna idea wizualna: Flow & Control (harmonijny przepływ danych połączony z bezwzględną
  stabilnością systemu).
- Osobowość marki: niezawodny, precyzyjny, nowoczesny, pragmatyczny, partnerski.
- Ton komunikacji: konkretny, biznesowy, ekspercki, bezpośredni — bez korporacyjnego żargonu
  i pustych obietnic.
- Emocje i skojarzenia wywoływane: spokój kontroli, poczucie technologicznego wsparcia,
  pewność decyzji, nowoczesność.
- Skojarzenia unikane: przestarzałe oprogramowanie ERP, bałagan informacyjny, pstrokacizna,
  brak stabilności.

**4. Wybór kierunku kreatywnego**

Spośród trzech koncepcji (Analityczna Precyzja, Dynamiczny Przepływ, Nowoczesny Minimalizm)
wybrano Dynamiczny Przepływ (Flow & Control). Uzasadnienie: koncepcja ta najlepiej oddaje
istotę integracji marketplace'ów (wielokanałowe strumienie danych scalone w jedno okno
operacyjne). Zapewnia doskonałą czytelność w intensywnej pracy codziennej oraz nowoczesny,
wyróżniający się na tle konkurencji charakter.

**5. System wizualny**

5.1. Paleta kolorów:

- Kolor główny (Cobalt Flow): `#0284c7` (RGB 2, 132, 199). Główny akcent wizualny, elementy
  CTA, wyróżnienia w interfejsie.
- Kolor neutralny ciemny (Deep Slate): `#0f172a` (RGB 15, 23, 42). Nagłówki, teksty bazowe,
  głębokie tła w trybie ciemnym.
- Kolor uzupełniający / sukces (Success Emerald / Turkus): `#10b981` (w akcentach cyfrowych) /
  turkusowy wariant `#14b8a6` (RGB 16, 185, 129). Statusy poprawności, wskaźniki wzrostu,
  dynamika w sygnecie.
- Kolor neutralny jasny (Clean Canvas): `#f8fafc` (RGB 248, 250, 252). Tła kart, sekcji,
  kontenerów danych w interfejsie SaaS.

5.2. Typografia systemowa: główny font UI i nagłówków Inter (SIL Open Font License), zamiennik
`Arial, sans-serif`; font tekstowy / raportowy Roboto, zamiennik `Helvetica, sans-serif`.
Hierarchia: H1 20–26pt Bold, -0.5px letter-spacing; H2 14pt SemiBold; tekst bazowy 10pt
Regular, line-height 1.4.

5.3. Motyw graficzny i siatka: nakładające się, płynne moduły i linie symbolizujące
synchronizację kanałów sprzedażowych; siatka oparta na module 8px.

**6. Specyfikacja technologiczna projektu logo**

6.1. Konstrukcja: znak składa się z geometrycznego sygnetu (abstrakcyjna litera „A" utworzona
przez dwa przenikające się strumienie danych zakończone dynamiczną strzałką wznoszącą) oraz
precyzyjnego logotypu ANVERO zapisanego krojem bazującym na Inter Bold, z dopiskiem Sales
Management System jako subtelnym opisem.

6.2. Pole ochronne: wokół całego logo minimalna strefa bezpieczna równa wysokości litery „A"
z głównego logotypu (1x u góry, u dołu, z lewej i prawej strony).

6.3. Warianty znaków:

1. Full Color Horizontal (poziomy): sygnet po lewej, logotyp po prawej. Podstawowa wersja do
   zastosowań cyfrowych i nagłówków dokumentów.
2. Full Color Stacked (pionowy / blokowy): sygnet nad logotypem. Do zastosowań o proporcjach
   zbliżonych do kwadratu (avatar, pieczęć).
3. Monochromatyczny / Teal: wersja jednobarwna do specjalnych zastosowań drukowanych.
4. Pure White (Negative): pełna biel na ciemnych tłach (np. Deep Slate `#0f172a` w trybie
   ciemnym).
5. Symbol / ikona (favicon): sam sygnet w kontenerze lub samodzielnie do zastosowań
   miniaturowych.

6.4. Minimalne rozmiary: ekran — szerokość minimalna układu poziomego 120 px (ikona 32×32 px);
druk — szerokość minimalna układu poziomego 25 mm (ikona 8 mm).
