# Dokument projektu — wersja startowa

## 1. Cel dokumentu

Ten dokument zawiera aktualny kontekst projektu oraz najważniejsze ustalenia dotyczące jego rozwoju. Ma umożliwić przeniesienie pracy na inne konto ChatGPT, inny komputer lub do innego narzędzia AI bez konieczności ponownego wyjaśniania całej koncepcji.

Projekt będzie rozwijany etapami. Na początku ma służyć przede wszystkim jako praktyczne narzędzie wspierające codzienną pracę, a w dalszej perspektywie może zostać rozbudowany lub przekształcony w produkt komercyjny.

---

# 2. Główna idea projektu

Planowane jest stworzenie własnej aplikacji do wspierania obsługi sprzedaży internetowej i zamówień z różnych platform marketplace.

Aplikacja ma docelowo umożliwiać między innymi:

* pobieranie zamówień z różnych platform,
* prezentowanie zamówień w jednym, wspólnym panelu,
* ujednolicenie obsługi zamówień niezależnie od ich źródła,
* obsługę statusów zamówień,
* integrację z systemami wysyłkowymi,
* przekazywanie informacji o przesyłkach,
* potencjalną integrację z systemami fakturowania,
* zarządzanie produktami, stanami magazynowymi i innymi procesami, jeśli będzie to potrzebne.

Pierwszymi rozważanymi integracjami są:

* Allegro,
* ERLI.

W przyszłości mogą zostać dodane kolejne platformy, przewoźnicy, systemy księgowe, programy magazynowe lub inne usługi.

---

# 3. Założenie strategiczne

Nie planujemy od razu tworzyć pełnego konkurenta dla BaseLinkera ani odtwarzać wszystkich jego funkcji.

Gotowe systemy posiadają bardzo dużą liczbę integracji i są rozwijane przez duże zespoły. Próba skopiowania całego takiego rozwiązania od początku byłaby niepotrzebnie skomplikowana.

Plan jest następujący:

1. Zidentyfikować konkretne problemy występujące w codziennej pracy.
2. Stworzyć rozwiązanie dopasowane do rzeczywistych potrzeb.
3. Zbudować małą, działającą wersję aplikacji.
4. Testować ją na prawdziwych procesach.
5. Rozbudowywać system tylko wtedy, gdy pojawi się konkretna potrzeba.

Aplikacja ma być rozwijana modułowo. Nie należy dodawać funkcji wyłącznie dlatego, że posiada je BaseLinker lub inne rozwiązanie komercyjne.

---

# 4. Możliwa przyszłość komercyjna

Na obecnym etapie głównym celem nie jest sprzedaż aplikacji.

Pierwsza wersja ma przede wszystkim:

* usprawniać pracę,
* oszczędzać czas,
* zmniejszać liczbę błędów,
* uporządkować obsługę zamówień,
* stanowić praktyczny projekt rozwojowy.

Jeżeli aplikacja okaże się skuteczna i inne firmy będą miały podobne potrzeby, można później rozważyć:

* sprzedaż dostępu w modelu abonamentowym,
* stworzenie produktu SaaS,
* sprzedaż licencji,
* tworzenie wersji dostosowanych do konkretnych firm,
* oferowanie dodatkowych modułów lub integracji.

Nie należy jednak projektować pierwszej wersji tak, jakby od początku miała obsługiwać tysiące klientów. Najpierw ma dobrze działać w rzeczywistym środowisku.

---

# 5. Planowana architektura

Wstępnie zakładany jest następujący podział:

## Frontend

Frontend będzie odpowiadał za:

* wygląd aplikacji,
* widoki i ekrany,
* wyświetlanie zamówień,
* formularze,
* filtrowanie i wyszukiwanie,
* interakcję użytkownika z systemem.

Planowane technologie:

* HTML,
* CSS,
* JavaScript.

Kod powinien być od początku uporządkowany.

Przykładowy podział:

```text
projekt/
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
```

Nie należy umieszczać całego HTML, CSS i JavaScript w jednym pliku, jeśli nie ma ku temu konkretnego powodu.

Frontend powinien być tworzony zgodnie z aktualnymi dobrymi praktykami:

* poprawna struktura dokumentu HTML,
* semantyczne elementy,
* odpowiednie nagłówki,
* poprawne formularze i etykiety,
* podstawowa dostępność,
* responsywny wygląd,
* czytelna struktura kodu,
* oddzielenie logiki od wyglądu.

---

## Backend

Backend będzie odpowiadał za:

* komunikację z API Allegro,
* komunikację z API ERLI,
* pobieranie i przetwarzanie zamówień,
* zapisywanie danych,
* logikę biznesową,
* autoryzację,
* komunikację pomiędzy frontendem a bazą danych,
* przyszłe integracje.

Wstępnie rozważany język:

* Python.

Dokładny framework backendowy zostanie wybrany później. Możliwe rozwiązania to między innymi:

* FastAPI,
* Django.

Na obecnym etapie nie należy wybierać technologii bez wcześniejszego przeanalizowania potrzeb.

---

## Baza danych

Wstępnie planowana baza:

* PostgreSQL.

Baza będzie przechowywać między innymi:

* zamówienia,
* produkty,
* dane dotyczące integracji,
* statusy,
* informacje o przesyłkach,
* dane potrzebne do działania aplikacji.

Dokładny model danych zostanie zaprojektowany przed rozpoczęciem implementacji właściwych funkcji.

---

# 6. Integracje z Allegro i ERLI

Integracje powinny być tworzone jako niezależne moduły.

Przykładowa koncepcja:

```text
backend/
├── integrations/
│   ├── allegro/
│   └── erli/
```

Każda integracja powinna odpowiadać za komunikację z konkretną platformą.

Aplikacja nie powinna mieszać logiki Allegro i ERLI bezpośrednio w jednym miejscu.

Docelowo system powinien przekształcać dane z różnych platform do wspólnego formatu wewnętrznego.

Przykład:

```text
Zamówienie z Allegro
        ↓
Moduł Allegro
        ↓
Wspólny format zamówienia
        ↓
Baza danych i panel aplikacji

Zamówienie z ERLI
        ↓
Moduł ERLI
        ↓
Wspólny format zamówienia
        ↓
Baza danych i panel aplikacji
```

Dzięki temu użytkownik aplikacji będzie obsługiwał zamówienia w podobny sposób niezależnie od platformy.

---

# 7. Obsługa wysyłek

Nie planujemy tworzyć własnych systemów kurierskich.

Jeżeli Allegro lub inny dostawca udostępnia odpowiednie API, aplikacja będzie korzystać z oficjalnych interfejsów API.

Możliwe przyszłe funkcje:

* tworzenie przesyłek,
* wybór metody dostawy,
* pobieranie danych przesyłki,
* pobieranie lub generowanie etykiet,
* przekazywanie numerów śledzenia,
* aktualizacja statusów wysyłki.

Integracje wysyłkowe powinny być dodawane tylko wtedy, gdy są rzeczywiście potrzebne.

---

# 8. Środowisko programistyczne

Na początku aplikacja będzie uruchamiana lokalnie na komputerze.

Nie ma potrzeby stawiania lokalnego serwera Apache.

Planowane środowisko:

* Windows,
* Visual Studio Code lub Kiro,
* Python,
* PostgreSQL,
* Git,
* GitHub.

Frontend i backend będą uruchamiane lokalnie na adresach typu:

```text
http://localhost
```

lub:

```text
http://127.0.0.1
```

Współczesne narzędzia programistyczne posiadają własne serwery deweloperskie, dlatego nie ma potrzeby instalowania Apache wyłącznie po to, aby uruchomić projekt lokalnie.

---

# 9. Docker

Docker został omówiony jako narzędzie umożliwiające uruchamianie aplikacji i jej zależności w uporządkowanych, odizolowanych środowiskach.

Docker może być przydatny później, ponieważ ułatwia:

* przenoszenie aplikacji między komputerami,
* utrzymanie tych samych wersji środowiska,
* uruchamianie bazy danych,
* wdrażanie aplikacji na serwerze.

Na początku Docker nie jest wymagany.

Plan:

1. Najpierw uruchomić aplikację natywnie na komputerze.
2. Zrozumieć podstawy działania aplikacji.
3. Dodać Docker później, gdy pojawi się konkretna potrzeba.

---

# 10. Visual Studio Code i Kiro

Rozważane są dwa środowiska:

## Visual Studio Code

Zalety:

* popularny standard,
* duża liczba rozszerzeń,
* dobra dokumentacja,
* łatwa integracja z GitHubem,
* szerokie wsparcie dla Pythona, HTML, CSS i JavaScript.

## Kiro

Kiro jest osobnym środowiskiem programistycznym opartym na technologii Code - OSS i posiada rozbudowane funkcje AI.

Może być używany jako główny edytor zamiast standardowego VS Code.

Projekt pozostaje niezależny od edytora. Ten sam folder projektu może być otwierany zarówno w Kiro, jak i w Visual Studio Code.

Na późniejszym etapie należy przetestować oba rozwiązania i wybrać to, które będzie wygodniejsze.

---

# 11. Planowane rozszerzenia edytora

Na początku nie należy instalować dużej liczby dodatków.

Wstępnie przydatne mogą być:

* Python,
* Pylance,
* Prettier,
* ESLint,
* rozszerzenie do podglądu stron lokalnych,
* integracja z GitHubem,
* narzędzia do obsługi PostgreSQL.

Docker i dodatkowe narzędzia mogą zostać dodane później.

Warto włączyć automatyczne formatowanie kodu podczas zapisu.

---

# 12. Wykorzystanie AI

ChatGPT będzie wykorzystywany przede wszystkim do:

* omawiania pomysłu,
* projektowania architektury,
* planowania funkcji,
* tworzenia modelu danych,
* wyjaśniania kodu,
* analizowania problemów,
* projektowania integracji,
* przeglądu i poprawy kodu.

Narzędzia AI działające bezpośrednio w edytorze, takie jak Kiro, mogą być używane później do:

* implementacji konkretnych funkcji,
* edycji wielu plików,
* refaktoryzacji,
* wyszukiwania błędów,
* przyspieszania codziennej pracy z kodem.

Nie należy generować dużych fragmentów projektu bez zrozumienia ich działania.

Kod powinien być:

* czytelny,
* wyjaśniony,
* uporządkowany,
* możliwy do dalszego rozwijania.

---

# 13. Git i GitHub

Git będzie używany do kontroli wersji projektu.

Git działa lokalnie na komputerze i śledzi zmiany w plikach.

GitHub będzie wykorzystywany jako zdalne miejsce przechowywania repozytorium.

Podstawowe pojęcia:

* `commit` — zapis logicznego etapu pracy w historii projektu,
* `push` — wysłanie commitów na GitHub,
* `pull` — pobranie zmian z GitHuba,
* `clone` — pobranie repozytorium na komputer.

Git nie tworzy automatycznie osobnej wersji po każdej zmianie w HTML lub innym pliku.

Programista sam decyduje, kiedy utworzyć commit.

Przykładowe commity:

```text
Dodano podstawowy ekran logowania

Dodano strukturę panelu zamówień

Dodano połączenie z bazą danych

Dodano pobieranie zamówień z Allegro
```

Zalecana zasada:

> Po zakończeniu większego, logicznego fragmentu pracy należy utworzyć commit.

Nie należy tworzyć jednego commitu obejmującego kilka tygodni pracy, ale nie trzeba też tworzyć commitu po każdej pojedynczej zmianie.

Na początek darmowy plan GitHub powinien być wystarczający.

Repozytorium projektu prawdopodobnie będzie prywatne.

---

# 14. Nazwa projektu lub przyszłej marki

Planowane jest stworzenie jednej spójnej nazwy, która może być używana dla:

* projektu,
* przyszłej marki lub firmy,
* konta GitHub,
* adresu e-mail,
* domeny internetowej,
* kolejnych aplikacji.

Nazwa powinna:

* być łatwa do wymówienia,
* być łatwa do zapamiętania,
* dobrze wyglądać w języku polskim i angielskim,
* nie ograniczać projektu wyłącznie do Allegro lub obsługi zamówień,
* umożliwiać rozwój w kierunku innych aplikacji,
* nie być myląco podobna do istniejącej firmy.

Przed wyborem należy sprawdzić:

* dostępność domeny `.pl`,
* dostępność domeny `.com`,
* dostępność nazwy użytkownika na GitHubie,
* obecność podobnych firm,
* potencjalne konflikty z istniejącymi markami.

Nie należy zakładać kont ani kupować domeny przed sprawdzeniem nazwy.

---

# 15. Spójna tożsamość projektu

Po wyborze nazwy można utworzyć:

1. dedykowany adres e-mail,
2. konto GitHub,
3. prywatne repozytorium,
4. nazwę projektu,
5. podstawową strukturę organizacyjną.

Wszystkie elementy powinny korzystać z tej samej lub możliwie podobnej nazwy.

Przykładowa struktura:

```text
NazwaMarki
├── GitHub: nazwamarki
├── e-mail: nazwamarki@...
├── domena: nazwamarki.pl
└── projekt: nazwa-aplikacji
```

---

# 16. Wstępna kolejność prac

Po rozpoczęciu pracy przy komputerze należy działać etapami.

Proponowana kolejność:

1. Sprawdzić, na którym koncie ChatGPT znajduje się aktywny plan.
2. Przenieść ten dokument na właściwe konto, jeśli będzie to potrzebne.
3. Wybrać nazwę marki lub projektu.
4. Sprawdzić dostępność nazwy.
5. Utworzyć dedykowany adres e-mail, jeśli zostanie podjęta taka decyzja.
6. Założyć konto GitHub.
7. Utworzyć prywatne repozytorium.
8. Wybrać między Visual Studio Code a Kiro.
9. Zainstalować potrzebne narzędzia.
10. Zainstalować i skonfigurować Python.
11. Zainstalować PostgreSQL.
12. Utworzyć lokalny folder projektu.
13. Podłączyć projekt do GitHub.
14. Utworzyć podstawową strukturę frontendową i backendową.
15. Uruchomić pierwszą lokalną wersję aplikacji.
16. Dopiero później rozpocząć integrację z API Allegro i ERLI.

---

# 17. Zasady rozwoju

Podczas tworzenia projektu należy przestrzegać następujących zasad:

* nie komplikować rozwiązania bez potrzeby,
* rozwijać aplikację etapami,
* najpierw tworzyć małą działającą wersję,
* każdą większą funkcję planować przed implementacją,
* utrzymywać czytelną strukturę plików,
* oddzielać frontend, backend i bazę danych,
* nie kopiować bez zrozumienia dużych fragmentów kodu,
* dokumentować ważne decyzje,
* tworzyć regularne commity,
* nie dodawać wszystkich możliwych integracji na początku,
* testować funkcje na rzeczywistych procesach,
* wybierać rozwiązania łatwe do utrzymania i rozbudowy.

---

# 18. Aktualny status

Na obecnym etapie:

* koncepcja projektu została wstępnie omówiona,
* kierunek technologiczny został określony,
* nie rozpoczęto jeszcze konfiguracji środowiska,
* nie utworzono jeszcze repozytorium,
* nie wybrano jeszcze nazwy marki,
* nie wybrano ostatecznie edytora,
* nie rozpoczęto jeszcze implementacji.

Następny etap:

> Po uruchomieniu ChatGPT na właściwym koncie należy przeanalizować ten dokument, potwierdzić aktualne założenia i rozpocząć konfigurację środowiska krok po kroku.

---

# 19. Instrukcja dla nowego czatu ChatGPT

Po wklejeniu tego dokumentu należy przekazać następującą informację:

„To jest dokument opisujący projekt, nad którym chcę pracować. Chcę kontynuować od momentu przygotowania środowiska programistycznego. Prowadź mnie krok po kroku i podawaj tylko następny potrzebny etap, ponieważ będę wykonywał konfigurację bezpośrednio na komputerze. Nie zakładaj, że znam programowanie — wyjaśniaj pojęcia, ale zachowuj dobre praktyki i docelową możliwość rozbudowy projektu.”

# Dokumentacja projektu

Szczegółowa dokumentacja znajduje się w katalogu docs/.

PROJECT_CONTEXT.md – główna wizja projektu
MVP.md – zakres pierwszej wersji
ARCHITECTURE.md – architektura systemu
DATABASE.md – model danych
API.md – dokumentacja API
ROADMAP.md – plan rozwoju
DECISIONS.md – historia ważnych decyzji