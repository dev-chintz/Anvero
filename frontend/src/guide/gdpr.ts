/**
 * What the GDPR tab says (docs/GDPR.md, docs/GUIDE.md).
 *
 * Two kinds of text. The **notice to buyers** and the **register of processing activities** are legal
 * texts for Polish buyers and for the Polish authority, so they are in Polish whatever language the
 * interface is in; they are built from what the application really does and from the controller's
 * details the owner entered, with a visible placeholder for what is still missing. The **team's part**
 * (what is held and why, how to answer a request, what to do after a breach, the security measures) is
 * in both interface languages. None of it is legal advice: the tab says so, and lists what the owner
 * should settle with a lawyer.
 */

import type { Language } from "../i18n";

export interface Controller {
  name: string | null;
  tax_id: string | null;
  address: string | null;
  email: string | null;
  phone: string | null;
  dpo_contact: string | null;
}

export interface Retention {
  orders_years: number;
  contacts_years: number;
}

/** What a field of the controller's details is called, for the list of what is missing. */
export const CONTROLLER_FIELDS: (keyof Controller)[] = ["name", "address", "tax_id", "email", "phone", "dpo_contact"];
/** The fields a notice cannot do without; the data protection officer and the phone are optional. */
export const REQUIRED_CONTROLLER_FIELDS: (keyof Controller)[] = ["name", "address", "email"];

export function missingControllerFields(controller: Controller): (keyof Controller)[] {
  return REQUIRED_CONTROLLER_FIELDS.filter((field) => !controller[field]);
}

const BLANK: Record<keyof Controller, string> = {
  name: "[uzupełnij: nazwa i forma prawna firmy]",
  tax_id: "[uzupełnij: NIP]",
  address: "[uzupełnij: adres siedziby]",
  email: "[uzupełnij: e-mail do spraw danych osobowych]",
  phone: "[uzupełnij: telefon]",
  dpo_contact: "",
};

function field(controller: Controller, name: keyof Controller): string {
  return controller[name] ?? BLANK[name];
}

// ---- the notice to buyers -----------------------------------------------------------------------

export type Block = { kind: "title" | "heading" | "paragraph"; text: string } | { kind: "list"; items: string[] };

/** The years as Polish counts them ("1 rok", "2 lata", "5 lat"). */
export function years(count: number): string {
  if (count === 1) return "1 rok";
  const lastDigit = count % 10;
  const lastTwo = count % 100;
  return lastDigit >= 2 && lastDigit <= 4 && !(lastTwo >= 12 && lastTwo <= 14) ? `${count} lata` : `${count} lat`;
}

/**
 * The notice a buyer is owed under art. 13 and 14 of the GDPR (the data comes from the marketplace,
 * not from the buyer, so art. 14 applies too), as blocks to show and to copy.
 */
export function buyerNotice(controller: Controller, retention: Retention): Block[] {
  const orders = years(retention.orders_years);
  const contacts = years(retention.contacts_years);
  const taxId = controller.tax_id ? `, NIP ${controller.tax_id}` : "";
  const phone = controller.phone ? `, tel. ${controller.phone}` : "";
  return [
    { kind: "title", text: "Informacja o przetwarzaniu danych osobowych kupujących (art. 13 i 14 RODO)" },
    { kind: "heading", text: "1. Administrator danych" },
    {
      kind: "paragraph",
      text: `Administratorem Twoich danych osobowych jest ${field(controller, "name")}, ${field(controller, "address")}${taxId} (dalej: Administrator). W sprawach dotyczących danych osobowych możesz się z nami skontaktować pod adresem e-mail ${field(controller, "email")}${phone}.`,
    },
    {
      kind: "paragraph",
      text: controller.dpo_contact
        ? `Administrator wyznaczył inspektora ochrony danych: ${controller.dpo_contact}.`
        : "Administrator nie wyznaczył inspektora ochrony danych.",
    },
    { kind: "heading", text: "2. Skąd mamy Twoje dane" },
    {
      kind: "paragraph",
      text: "Dane otrzymujemy od Ciebie za pośrednictwem platformy sprzedażowej (Allegro lub Erli), na której złożyłeś zamówienie, oraz od przewoźnika (informacje o przesyłce). Ta platforma jest odrębnym administratorem Twoich danych i to ona informuje Cię o swoim przetwarzaniu.",
    },
    { kind: "heading", text: "3. Jakie dane przetwarzamy, w jakim celu i jak długo" },
    {
      kind: "list",
      items: [
        "Realizacja zamówienia i wysyłka (art. 6 ust. 1 lit. b RODO, czyli wykonanie umowy sprzedaży): imię i nazwisko, login na platformie, adres e-mail i numer telefonu, adres dostawy lub punkt odbioru, treść zamówienia i Twoja wiadomość do sprzedawcy. Dane przechowujemy do czasu realizacji zamówienia, a następnie tak długo, jak wymagają tego przepisy opisane poniżej.",
        `Obowiązki podatkowe i rachunkowe (art. 6 ust. 1 lit. c RODO, czyli obowiązek prawny, m.in. przepisy Ordynacji podatkowej i o ewidencji sprzedaży): dane z zamówienia, dane na fakturze lub w ewidencji sprzedaży (imię, nazwisko lub nazwa firmy, adres, NIP firmy) oraz kwoty i daty płatności. Dane przechowujemy przez ${orders}, licząc od końca roku, w którym powstał obowiązek podatkowy.`,
        `Obsługa wiadomości, zwrotów, reklamacji i sporów (art. 6 ust. 1 lit. b RODO oraz lit. f, czyli nasz prawnie uzasadniony interes polegający na dochodzeniu roszczeń i obronie przed nimi): login, adres e-mail, treść wiadomości i zgłoszenia. Dane przechowujemy przez ${contacts} od ostatniej wiadomości, a w sprawach zwrotów i reklamacji od ich zamknięcia.`,
        "Bezpieczeństwo danych i ciągłość działalności (art. 6 ust. 1 lit. f RODO): kopie zapasowe zawierające powyższe dane, przechowywane w rotacji do około trzech miesięcy. Dane usunięte z systemu mogą więc przez ten czas pozostawać w starszych kopiach.",
      ],
    },
    {
      kind: "paragraph",
      text: "Po upływie tych okresów dane osobowe są z zamówień usuwane automatycznie, a pozostają informacje, które nie wskazują na osobę (np. kwoty, produkty, daty).",
    },
    { kind: "heading", text: "4. Komu przekazujemy dane" },
    {
      kind: "paragraph",
      text: "Odbiorcami danych mogą być: przewoźnicy i firmy kurierskie realizujące dostawę (m.in. InPost oraz przewoźnicy usługi Wysyłam z Allegro); biuro rachunkowe lub księgowa Administratora; dostawca usługi przechowywania kopii zapasowych; platformy, przez które sprzedajemy (Allegro, Erli), w zakresie niezbędnym do obsługi zamówienia; oraz organy publiczne, jeśli wymagają tego przepisy prawa.",
    },
    { kind: "heading", text: "5. Przekazywanie danych poza Europejski Obszar Gospodarczy" },
    {
      kind: "paragraph",
      text: "Co do zasady nie przekazujemy danych poza EOG. Wyjątkiem może być zaszyfrowana kopia zapasowa przechowywana u dostawcy usług chmurowych, który może przetwarzać dane poza EOG; kopia jest zaszyfrowana.",
    },
    { kind: "heading", text: "6. Twoje prawa" },
    {
      kind: "paragraph",
      text: "Masz prawo dostępu do swoich danych, ich sprostowania, usunięcia (z zastrzeżeniem danych, które musimy przechowywać na mocy prawa), ograniczenia przetwarzania oraz przenoszenia danych. Masz też prawo sprzeciwu wobec przetwarzania opartego na naszym prawnie uzasadnionym interesie. Odpowiemy na Twoje żądanie bez zbędnej zwłoki, nie później niż w ciągu miesiąca.",
    },
    {
      kind: "paragraph",
      text: "Masz prawo wnieść skargę do organu nadzorczego: Prezesa Urzędu Ochrony Danych Osobowych, ul. Stawki 2, 00-193 Warszawa.",
    },
    { kind: "heading", text: "7. Dobrowolność podania danych i zautomatyzowane decyzje" },
    {
      kind: "paragraph",
      text: "Podanie danych jest dobrowolne, ale niezbędne do zawarcia i wykonania umowy sprzedaży oraz dostarczenia zamówienia. Nie podejmujemy wobec Ciebie decyzji w sposób zautomatyzowany i nie profilujemy Cię.",
    },
  ];
}

/** The notice as plain text, to copy. */
export function noticeText(blocks: Block[]): string {
  return blocks
    .map((block) => {
      if (block.kind === "list") return block.items.map((item) => `- ${item}`).join("\n");
      if (block.kind === "heading") return `\n${block.text}`;
      return block.text;
    })
    .join("\n")
    .trim();
}

// ---- the register of processing activities (art. 30 ust. 1) --------------------------------------

export interface RegisterRow {
  activity: string;
  purpose: string;
  subjects: string;
  data: string;
  recipients: string;
  transfers: string;
  retention: string;
}

/** The register's rows: one per processing activity, each with the elements art. 30 ust. 1 asks for. */
export function registerRows(retention: Retention): RegisterRow[] {
  const orders = `${years(retention.orders_years)} od końca roku, w którym powstał obowiązek podatkowy; potem dane osobowe są usuwane z zamówienia`;
  const contacts = years(retention.contacts_years);
  return [
    {
      activity: "Obsługa zamówień i wysyłka",
      purpose: "Realizacja umów sprzedaży zawartych na Allegro i Erli, przygotowanie i wysyłka zamówień (art. 6 ust. 1 lit. b RODO).",
      subjects: "Kupujący.",
      data: "Imię i nazwisko, login na platformie, e-mail (adres pośredniczący platformy), telefon, adres dostawy lub punkt odbioru, treść zamówienia, wiadomość do sprzedawcy, notatki.",
      recipients: "Allegro i Erli (odrębni administratorzy), InPost, przewoźnicy usługi Wysyłam z Allegro.",
      transfers: "Nie.",
      retention: orders,
    },
    {
      activity: "Dokumentacja podatkowa i księgowa",
      purpose: "Faktury, ewidencja sprzedaży zwolnionej z kasy rejestrującej, raporty dla księgowej (art. 6 ust. 1 lit. c RODO).",
      subjects: "Kupujący (osoby prywatne i firmy).",
      data: "Imię i nazwisko lub nazwa firmy, adres kupującego, NIP firmy, kwoty, daty i operator płatności.",
      recipients: "Księgowa lub biuro rachunkowe (eksporty CSV, Excel, PDF), organy podatkowe.",
      transfers: "Nie.",
      retention: `${years(retention.orders_years)} od końca roku, w którym powstał obowiązek podatkowy; dane kupującego w ewidencji są wtedy usuwane, kwoty zostają.`,
    },
    {
      activity: "Wiadomości od kupujących",
      purpose: "Odpowiadanie kupującym (art. 6 ust. 1 lit. b i f RODO).",
      subjects: "Kupujący.",
      data: "Login na platformie, treść wiadomości.",
      recipients: "Allegro (platforma, przez którą idą wiadomości).",
      transfers: "Nie.",
      retention: `${contacts} od ostatniej wiadomości.`,
    },
    {
      activity: "Zwroty, reklamacje i spory",
      purpose: "Obsługa zwrotów, reklamacji i sporów, obrona i dochodzenie roszczeń (art. 6 ust. 1 lit. b, c i f RODO).",
      subjects: "Kupujący.",
      data: "Login, e-mail, treść zgłoszenia i powód, dane zamówienia.",
      recipients: "Allegro.",
      transfers: "Nie.",
      retention: `${contacts} od otwarcia sprawy, liczone po jej zamknięciu.`,
    },
    {
      activity: "Zapis tego, co wysłano do marketplace'ów i przewoźników",
      purpose: "Dowód wykonania i kontrola zmian wysłanych do Allegro, Erli i przewoźników (art. 6 ust. 1 lit. f RODO).",
      subjects: "Kupujący (odbiorcy przesyłek).",
      data: "Odbiorca etykiety, treść wysłanej odpowiedzi.",
      recipients: "Allegro, Erli, InPost (to, co do nich wysłano).",
      transfers: "Nie.",
      retention: `${contacts}, albo razem z zamówieniem, jeśli dotyczy tylko jego.`,
    },
    {
      activity: "Konta użytkowników aplikacji",
      purpose: "Zarządzanie dostępem do aplikacji i jego zabezpieczenie (art. 6 ust. 1 lit. f RODO).",
      subjects: "Osoby pracujące w aplikacji (administrator i współpracownicy).",
      data: "Adres e-mail, skrót hasła, rola i uprawnienia, informacja, kto zmienił status zamówienia.",
      recipients: "Brak.",
      transfers: "Nie.",
      retention: "Do usunięcia konta; historia zmian zamówień zostaje bez wskazania konta.",
    },
    {
      activity: "Kopie zapasowe",
      purpose: "Bezpieczeństwo danych i ciągłość działalności (art. 6 ust. 1 lit. f RODO).",
      subjects: "Osoby, których dane są w pozostałych czynnościach.",
      data: "Wszystkie dane z powyższych czynności, w stanie z danej nocy.",
      recipients: "Dostawca usługi przechowywania kopii zapasowych (kopia zewnętrzna jest zaszyfrowana).",
      transfers: "Możliwe: dostawca chmury może przetwarzać dane poza EOG; kopia jest zaszyfrowana. Podstawę przekazania ustal z prawnikiem.",
      retention: "Rotacja: 7 kopii dziennych, 4 tygodniowe i 3 miesięczne, czyli do około trzech miesięcy.",
    },
  ];
}

/** The security measures of art. 32, as the register's last element and the team's part both give them. */
export interface TextByLanguage {
  pl: string[];
  en: string[];
}

export const SECURITY_MEASURES: TextByLanguage = {
  pl: [
    "Dostęp do aplikacji wymaga logowania; uprawnienia nadaje się osobno dla każdego obszaru (zamówienia, wiadomości, zwroty, etykiety, finanse, integracje), a konta zakłada tylko administrator.",
    "Hasła są przechowywane wyłącznie jako skróty, a tokeny i klucze integracji (Allegro, InPost) można przechowywać zaszyfrowane.",
    "Aplikacja działa na serwerze Administratora i jest dostępna z sieci domowej lub przez szyfrowany tunel VPN (Tailscale), nie z otwartego internetu.",
    "Dane osobowe są automatycznie usuwane z zamówień, wiadomości, spraw i ewidencji po upływie okresu przechowywania.",
    "Dane kupujących nie trafiają do dziennika aplikacji; wyszukiwane frazy (często nazwisko lub login) nie zostają w adresie strony ani w historii przeglądarki.",
    "Kopie zapasowe wykonywane są co noc, w rotacji, a kopia zewnętrzna jest zaszyfrowana.",
    "Zmiany wysyłane do marketplace'ów można wstrzymać trybem bezpiecznym i są zapisywane w dzienniku.",
  ],
  en: [
    "Access to the application needs a login; permissions are given separately for each area (orders, messages, returns, labels, finance, integrations), and only an administrator creates accounts.",
    "Passwords are stored only as hashes, and the integration tokens and keys (Allegro, InPost) can be stored encrypted.",
    "The application runs on the controller's own server and is reachable from the home network or through an encrypted VPN tunnel (Tailscale), not from the open internet.",
    "Personal data is erased by itself from orders, messages, cases and the record once the retention period is over.",
    "Buyers' data does not go to the application log; a search (often a name or a login) is not left in the address or the browser's history.",
    "Backups are made every night, in rotation, and the off-site copy is encrypted.",
    "Changes sent to the marketplaces can be held back by safe mode, and are recorded in a log.",
  ],
};

// ---- the team's part ---------------------------------------------------------------------------

export interface DataRow {
  data: string;
  where: string;
  why: string;
  kept: (retention: Retention) => string;
}

export interface Step {
  title: string;
  text: string;
  /** A command to run, shown as code. */
  command?: string;
}

export interface Checklist {
  title: string;
  text: string;
}

export interface GdprStaffContent {
  disclaimer: string;
  /** What the application holds, and why. */
  dataIntro: string;
  dataColumns: { data: string; where: string; why: string; kept: string };
  data: DataRow[];
  recipientsIntro: string;
  recipients: { name: string; text: string }[];
  requestIntro: string;
  requests: Step[];
  requestNote: string;
  breachIntro: string;
  breach: Step[];
  securityIntro: string;
  checklistIntro: string;
  checklist: Checklist[];
}

export const gdprStaffPl: GdprStaffContent = {
  disclaimer:
    "To opis tego, co faktycznie robi aplikacja, i projekty dokumentów do sprawdzenia, a nie porada prawna. Administratorem danych jest właściciel firmy: z prawnikiem, księgową lub inspektorem ochrony danych ustal to, co wymieniono w liście „Do ustalenia”, zanim zaczniesz polegać na tych tekstach.",
  dataIntro: "Co aplikacja przechowuje o osobach, po co i jak długo. Okresy są takie, jakich używa automatyczne usuwanie danych.",
  dataColumns: { data: "Dane", where: "Gdzie", why: "Po co", kept: "Jak długo" },
  data: [
    { data: "Login, e-mail, imię i nazwisko, firma, telefon kupującego", where: "Zamówienia", why: "Realizacja sprzedaży (umowa)", kept: (r) => `${years(r.orders_years)} od końca roku podatkowego` },
    { data: "Adresy dostawy, faktury i punktu odbioru, NIP", where: "Adresy zamówień", why: "Wysyłka; fakturowanie (obowiązek prawny)", kept: (r) => `jak zamówienie (${years(r.orders_years)})` },
    { data: "Wiadomość kupującego, notatki (marketplace'u i własna)", where: "Zamówienia", why: "Realizacja sprzedaży", kept: () => "jak zamówienie" },
    { data: "Wątki wiadomości: login i treść", where: "Wiadomości", why: "Odpowiadanie kupującym", kept: (r) => `${years(r.contacts_years)} od ostatniej wiadomości` },
    { data: "Zwroty, reklamacje, spory: login, e-mail, treść", where: "Zwroty i reklamacje", why: "Obsługa zgłoszenia (prawo konsumenckie)", kept: (r) => `${years(r.contacts_years)} od otwarcia, po zamknięciu` },
    { data: "To, co wysłano do marketplace'ów i InPost (odbiorca etykiety, treść odpowiedzi)", where: "Dziennik wysłanych zmian", why: "Dowód wykonania", kept: (r) => `${years(r.contacts_years)}, albo z zamówieniem` },
    { data: "Imię, nazwisko i adres kupującego w ewidencji bezrachunkowej", where: "Raport bezrachunkowy", why: "Ewidencja wymagana przepisami (obowiązek prawny)", kept: (r) => `${years(r.orders_years)}; nie jest usuwana na wniosek kupującego` },
    { data: "E-mail i skrót hasła osób pracujących w aplikacji", where: "Użytkownicy", why: "Logowanie", kept: () => "dopóki istnieje konto" },
  ],
  recipientsIntro: "Komu dane trafiają. Przy każdym podmiocie zapisz, czy jest odrębnym administratorem, czy przetwarza dane na Twoje zlecenie (to drugie wymaga umowy powierzenia).",
  recipients: [
    { name: "Allegro i Erli", text: "Stąd przychodzą zamówienia; każdy jest odrębnym administratorem. Anvero odsyła do nich statusy, numery przesyłek i odpowiedzi." },
    { name: "InPost i przewoźnicy Wysyłam z Allegro", text: "Przesyłka zawiera imię i nazwisko odbiorcy, e-mail, telefon i paczkomat lub adres." },
    { name: "Księgowa lub biuro rachunkowe", text: "Dostaje eksporty raportu bezrachunkowego (CSV, Excel, PDF) z kolumnami, które wybierzesz. Ustal, czy jest odrębnym administratorem, czy przetwarza dane na zlecenie." },
    { name: "Google Drive", text: "Zaszyfrowana kopia zapasowa nocnego zrzutu bazy, przechowywana poza serwerem." },
    { name: "Tailscale", text: "Przenosi zaszyfrowany ruch między laptopem a serwerem; nie widzi treści stron." },
  ],
  requestIntro:
    "Wniosek przychodzi zwykle od kupującego przez marketplace. Zidentyfikuj go po loginie na platformie (adresy e-mail Allegro są pośredniczące i różne dla każdego zamówienia) albo po adresie e-mail. Odpowiedz bez zbędnej zwłoki, najpóźniej w ciągu miesiąca (w sprawie złożonej można przedłużyć o dwa miesiące i trzeba o tym zawiadomić w pierwszym miesiącu). Skrypty uruchamiasz w terminalu kontenera „backend” na serwerze, jako python scripts/….",
  requests: [
    { title: "Dostęp do danych i ich przeniesienie (art. 15 i 20)", text: "Skrypt zapisuje wszystko, co o osobie mamy, w pliku JSON: zamówienia z adresami i pozycjami, przesyłki i etykiety, wysłane zmiany, wiersze ewidencji bezrachunkowej, wątki wiadomości i zgłoszenia. Plik przekaż osobie, a potem go usuń.", command: "python scripts/export_person.py --login LOGIN --out kupujacy.json" },
    { title: "Usunięcie danych (art. 17)", text: "Najpierw uruchom bez --apply, żeby zobaczyć, co zostanie usunięte; z --apply usuwa. Zamówienie, które jest jeszcze w okresie podatkowym, zachowuje dane z faktury firmowej i wiersze ewidencji bezrachunkowej (obowiązek prawny, art. 17 ust. 3 lit. b); po tym okresie usunie je automat. Nie da się tego cofnąć.", command: "python scripts/anonymize_person.py --login LOGIN\npython scripts/anonymize_person.py --login LOGIN --apply" },
    { title: "Sprostowanie (art. 16)", text: "Dane pochodzą z marketplace'u, a import je nadpisuje: popraw je tam. Własną notatkę zmienisz na stronie zamówienia." },
    { title: "Sprzeciw i ograniczenie (art. 21 i 18)", text: "Aplikacja nie prowadzi marketingu, więc sprzeciw ma niewiele do objęcia. Ograniczenie realizujesz, nie obsługując zamówienia, i zapisujesz to poza Anvero." },
    { title: "Zapisz wniosek", text: "Zanotuj datę, rodzaj wniosku i datę odpowiedzi (bez samych danych). Taki rejestr wniosków prowadzisz poza Anvero." },
  ],
  requestNote: "Usunięcie nie sięga kopii zapasowych już wykonanych: wygasają z rotacją w ciągu około trzech miesięcy. Po odtworzeniu kopii uruchom ponownie usuwanie danych i usunięcia z zapisanego rejestru wniosków.",
  breachIntro:
    "Naruszenie ochrony danych to utrata, wyciek, dostęp osoby niepowołanej albo zmiana danych osobowych (np. zgubiony laptop z dostępem, pomyłkowo wysłany plik, włamanie na konto). Czas jest krótki: trzeba działać od razu.",
  breach: [
    { title: "1. Powstrzymaj", text: "Odetnij dostęp: wyloguj i wyłącz konto, zmień hasła, w razie potrzeby wyłącz serwer z sieci. Włącz tryb bezpieczny, żeby nic nie szło do marketplace'ów." },
    { title: "2. Wymień sekrety, jeśli mogły wyciec", text: "Połącz konto Allegro od nowa (Ustawienia → Integracje), wygeneruj nowy klucz Erli i token InPost, a hasła kont zmień skryptem.", command: "python scripts/reset_password.py adres@example.com" },
    { title: "3. Oceń ryzyko", text: "Czyje dane, jakie (adresy i telefony czy tylko kwoty), ilu osób, czy były zaszyfrowane, czy ktoś je faktycznie zobaczył. Zapisz to." },
    { title: "4. Zgłoś do UODO w 72 godziny (art. 33)", text: "Jeśli naruszenie może skutkować ryzykiem dla praw lub wolności osób, zgłoś je Prezesowi UODO bez zbędnej zwłoki, w miarę możliwości w ciągu 72 godzin od stwierdzenia. Zgłoszenia robi się formularzem na stronie uodo.gov.pl. Gdy ryzyko jest niskie, zgłoszenie nie jest wymagane, ale decyzję i jej uzasadnienie zapisz." },
    { title: "5. Zawiadom osoby, jeśli ryzyko jest wysokie (art. 34)", text: "Gdy naruszenie może powodować wysokie ryzyko (np. wyciek adresów i telefonów), poinformuj osoby jasnym językiem: co się stało, jakie mogą być skutki, co zrobiliśmy i kogo pytać." },
    { title: "6. Udokumentuj (art. 33 ust. 5)", text: "Każde naruszenie, także niezgłoszone, zapisz w rejestrze naruszeń poza Anvero: co, kiedy, jakie dane, skutki, działania, decyzja o zgłoszeniu." },
  ],
  securityIntro: "Środki techniczne i organizacyjne, które aplikacja daje (art. 32). Są też w rejestrze czynności.",
  checklistIntro: "Rzeczy, które aplikacja zrobić za Ciebie nie może. Ustal je z prawnikiem, księgową lub inspektorem ochrony danych.",
  checklist: [
    { title: "Księgowa: administrator czy podmiot przetwarzający?", text: "Od tego zależy, czy potrzebna jest umowa powierzenia (art. 28). Wpisz to w rejestrze i klauzuli." },
    { title: "Podstawa przekazania do dostawcy chmury", text: "Kopia zapasowa na Google Drive może być przetwarzana poza EOG. Sprawdź, czy dostawca spełnia warunki przekazania, i uzupełnij to w klauzuli i rejestrze." },
    { title: "Gdzie pokazać klauzulę kupującym", text: "Zwykle w opisie sklepu na Allegro i Erli (zakładka o sprzedawcy lub regulamin) albo w dokumencie dołączonym do paczki. Sprawdź, co już podaje marketplace, żeby nie dublować." },
    { title: "Czy potrzebny jest inspektor ochrony danych", text: "Mała firma sprzedająca towary zwykle go nie wyznacza obowiązkowo. Jeśli go wyznaczysz, wpisz kontakt w Ustawieniach." },
    { title: "Rejestr wniosków i naruszeń", text: "Prowadzony poza Anvero (arkusz lub dokument): daty, rodzaj, odpowiedź. Anvero ich nie przechowuje." },
    { title: "Okresy przechowywania", text: "Aplikacja używa 5 lat od końca roku podatkowego dla zamówień i 2 lat dla wiadomości i spraw. Potwierdź je z księgową i prawnikiem." },
  ],
};

export const gdprStaffEn: GdprStaffContent = {
  disclaimer:
    "This describes what the application actually does and gives drafts of documents to check; it is not legal advice. The data controller is the company's owner: settle what the \"To settle\" list names with a lawyer, an accountant or a data protection officer before you rely on these texts.",
  dataIntro: "What the application holds about people, why and for how long. The periods are the ones the automatic erasure uses.",
  dataColumns: { data: "Data", where: "Where", why: "Why", kept: "For how long" },
  data: [
    { data: "The buyer's login, e-mail, name, company, phone", where: "Orders", why: "Fulfilling the sale (contract)", kept: (r) => `${r.orders_years} years after the end of the tax year` },
    { data: "Delivery, invoice and pickup-point addresses, tax id", where: "Order addresses", why: "Shipping; invoicing (legal duty)", kept: (r) => `as the order (${r.orders_years} years)` },
    { data: "The buyer's message, notes (the marketplace's and your own)", where: "Orders", why: "Fulfilling the sale", kept: () => "as the order" },
    { data: "Message threads: login and text", where: "Inbox", why: "Answering buyers", kept: (r) => `${r.contacts_years} years after the last message` },
    { data: "Returns, claims, disputes: login, e-mail, text", where: "Returns and claims", why: "Handling the case (consumer law)", kept: (r) => `${r.contacts_years} years after it was opened, once closed` },
    { data: "What was sent to the marketplaces and InPost (a label's recipient, a reply's text)", where: "Log of changes sent", why: "A record of what was sent", kept: (r) => `${r.contacts_years} years, or with the order` },
    { data: "The buyer's name and address in the non-invoiced record", where: "Sales report", why: "The record the law requires (legal duty)", kept: (r) => `${r.orders_years} years; not erased on the buyer's request` },
    { data: "E-mail and password hash of the people working in the application", where: "Users", why: "Logging in", kept: () => "while the account exists" },
  ],
  recipientsIntro: "Who the data goes to. For each, note whether it is a controller in its own right or processes the data on your behalf (the second needs a processing agreement).",
  recipients: [
    { name: "Allegro and Erli", text: "Where the orders come from; each is a controller in its own right. Anvero sends back statuses, tracking numbers and replies." },
    { name: "InPost and the Wysyłam z Allegro carriers", text: "A parcel carries the recipient's name, e-mail, phone and the locker or address." },
    { name: "The accountant", text: "Receives the sales report's exports (CSV, Excel, PDF) with the columns you choose. Settle whether they are a controller of their own or process the data for you." },
    { name: "Google Drive", text: "The encrypted off-site copy of the nightly database dump." },
    { name: "Tailscale", text: "Carries the encrypted traffic between a laptop and the server; it does not see the pages." },
  ],
  requestIntro:
    "A request usually comes from a buyer through the marketplace. Identify them by their login on the platform (Allegro's e-mails are masked and differ for each order) or by e-mail. Answer without undue delay and within a month at most (for a complex request it can be extended by two months, and you must say so within the first month). The scripts run in the terminal of the \"backend\" container on the server, as python scripts/….",
  requests: [
    { title: "Access and portability (art. 15 and 20)", text: "The script writes everything held about the person to a JSON file: orders with addresses and items, shipments and labels, what was sent, their rows of the non-invoiced record, message threads and cases. Hand the file over, then delete it.", command: "python scripts/export_person.py --login LOGIN --out buyer.json" },
    { title: "Erasure (art. 17)", text: "First run without --apply to see what would be erased; with --apply it erases. An order still inside its tax period keeps a company invoice's data and the rows of the non-invoiced record (a legal duty, art. 17(3)(b)); the automatic erasure removes them after the period. It cannot be undone.", command: "python scripts/anonymize_person.py --login LOGIN\npython scripts/anonymize_person.py --login LOGIN --apply" },
    { title: "Correction (art. 16)", text: "The data comes from the marketplace and an import replaces it: correct it there. Your own note is edited on the order page." },
    { title: "Objection and restriction (art. 21 and 18)", text: "The application does no marketing, so an objection has little to reach. A restriction is honoured by not handling the order, and recorded outside Anvero." },
    { title: "Record the request", text: "Note the date, the kind of request and the date of the answer (not the data itself). You keep such a register of requests outside Anvero." },
  ],
  requestNote: "Erasure does not reach a backup already made: it ages out with the rotation, within about three months. After restoring a backup, run the erasure again, and the erasures from your register of requests.",
  breachIntro:
    "A personal data breach is a loss, leak, access by someone not authorized, or alteration of personal data (a lost laptop with access, a file sent by mistake, a hacked account). Time is short: act at once.",
  breach: [
    { title: "1. Contain it", text: "Cut off access: log out and disable the account, change passwords, take the server off the network if need be. Switch safe mode on so nothing goes to the marketplaces." },
    { title: "2. Replace the secrets that may have leaked", text: "Connect the Allegro account again (Settings → Integrations), generate a new Erli key and InPost token, and change account passwords with the script.", command: "python scripts/reset_password.py address@example.com" },
    { title: "3. Assess the risk", text: "Whose data, what kind (addresses and phones, or only amounts), how many people, whether it was encrypted, whether anyone actually saw it. Write it down." },
    { title: "4. Report to the UODO within 72 hours (art. 33)", text: "If the breach may result in a risk to people's rights or freedoms, report it to the President of the UODO without undue delay and, where feasible, within 72 hours of becoming aware. The report is made with the form on uodo.gov.pl. Where the risk is unlikely, no report is needed, but write the decision and its reason down." },
    { title: "5. Tell the people if the risk is high (art. 34)", text: "Where the breach may cause a high risk (a leak of addresses and phones, say), tell the people in plain language: what happened, what the consequences may be, what has been done and whom to ask." },
    { title: "6. Document it (art. 33(5))", text: "Every breach, reported or not, goes in a register of breaches outside Anvero: what, when, what data, consequences, actions, the decision on reporting." },
  ],
  securityIntro: "The technical and organizational measures the application gives (art. 32). They are also in the register of activities.",
  checklistIntro: "Things the application cannot do for you. Settle them with a lawyer, an accountant or a data protection officer.",
  checklist: [
    { title: "The accountant: controller or processor?", text: "It decides whether a processing agreement is needed (art. 28). Put it in the register and the notice." },
    { title: "The basis for passing data to a cloud provider", text: "The Google Drive backup may be processed outside the EEA. Check that the provider meets the conditions for the transfer, and add it to the notice and the register." },
    { title: "Where to show the notice to buyers", text: "Usually in the shop's description on Allegro and Erli (the seller's tab or the terms), or in a document put in the parcel. Check what the marketplace already says, so as not to repeat it." },
    { title: "Whether a data protection officer is needed", text: "A small firm selling goods usually has no duty to appoint one. If you appoint one, put the contact in Settings." },
    { title: "The register of requests and breaches", text: "Kept outside Anvero (a sheet or a document): dates, kind, answer. Anvero does not keep them." },
    { title: "Retention periods", text: "The application uses 5 years from the end of the tax year for orders and 2 years for messages and cases. Confirm them with the accountant and the lawyer." },
  ],
};

export function staffFor(language: Language): GdprStaffContent {
  return language === "pl" ? gdprStaffPl : gdprStaffEn;
}

export function securityFor(language: Language): string[] {
  return language === "pl" ? SECURITY_MEASURES.pl : SECURITY_MEASURES.en;
}
