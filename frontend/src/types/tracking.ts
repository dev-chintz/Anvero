/**
 * Where a parcel can be followed on its carrier's own page.
 *
 * The carrier is known by an id (Allegro's `INPOST`, `POCZTA_POLSKA`; Erli's
 * lower-case vendor name) and often by a name as well (`InPost Kurier`), so
 * both are read as words and the first carrier recognised wins. A carrier
 * Anvero has no page for (`OTHER`, anything new) gets no link: the number is
 * still shown, as text.
 *
 * Parcels of Allegro's own delivery services (Kurier DPD, ORLEN Paczka, DHL BOX,
 * DPD Pickup, One Box, One Kurier) have the carrier id `ALLEGRO` and numbers
 * of Allegro's own making (`AD...`, `A...O...I...`). Those numbers are not the
 * carrier's, and the carrier's page does not know them (ORLEN Paczka and DPD say
 * so): they are followed on Allegro's own tracking pages, `AD...` on Allegro
 * Delivery's and the others on One's. Both pages are given the number as
 * `numer`; whether they read it from the address is not known (allegro.pl does
 * not answer automated requests), and one that does not still lands on the page
 * that asks for it.
 *
 * The addresses are the carriers' public tracking pages and were not opened
 * with a real number when written (`DECISIONS.md`); a carrier that moves its
 * page is a one-line change here.
 */
const TRACKING_PAGES: {
  words: string[];
  /** Whether this page follows that number; a carrier with no rule takes every number. */
  accepts?: (waybill: string) => boolean;
  url: (waybill: string) => string;
}[] = [
  // first: a name such as "Allegro Kurier DPD (AD)" holds the word DPD too, and
  // DPD's own page does not know an Allegro number. A number that is all digits
  // (an InPost parcel bought through Allegro) is the carrier's own.
  {
    words: ["allegro"],
    accepts: (n) => /^[a-z]/i.test(n),
    url: (n) =>
      /^ad/i.test(decodeURIComponent(n))
        ? `https://allegro.pl/allegrodelivery/sledzenie-paczki?numer=${n}`
        : `https://allegro.pl/kampania/one/kurier/sledzenie-paczki?numer=${n}`,
  },
  {
    words: ["inpost"],
    url: (n) => `https://inpost.pl/sledzenie-przesylek?number=${n}`,
  },
  {
    words: ["dpd"],
    url: (n) => `https://tracktrace.dpd.com.pl/parcelDetails?p1=${n}`,
  },
  {
    words: ["dhl"],
    url: (n) => `https://www.dhl.com/pl-pl/home/tracking.html?tracking-id=${n}`,
  },
  {
    words: ["poczta", "pocztex"],
    url: (n) => `https://emonitoring.poczta-polska.pl/?numer=${n}`,
  },
  {
    words: ["ups"],
    url: (n) => `https://www.ups.com/track?loc=pl_PL&tracknum=${n}`,
  },
  {
    words: ["gls"],
    url: (n) => `https://gls-group.com/PL/pl/sledzenie-paczek?match=${n}`,
  },
  {
    words: ["fedex"],
    url: (n) => `https://www.fedex.com/fedextrack/?trknbr=${n}`,
  },
];

function wordsOf(text: string | null | undefined): string[] {
  return (text ?? "").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
}

/** The carrier's tracking page for this number, or null when there is none to offer. */
export function trackingUrl(
  carrier: { carrier_id?: string | null; carrier_name?: string | null },
  waybill: string | null | undefined,
): string | null {
  const number = (waybill ?? "").trim();
  if (!number) return null;
  // the id is the marketplace's exact word for the carrier, so it is read first
  for (const source of [carrier.carrier_id, carrier.carrier_name]) {
    const words = wordsOf(source);
    const page = TRACKING_PAGES.find(
      (candidate) =>
        candidate.words.some((word) => words.includes(word)) &&
        (candidate.accepts?.(number) ?? true),
    );
    if (page) return page.url(encodeURIComponent(number));
  }
  return null;
}
