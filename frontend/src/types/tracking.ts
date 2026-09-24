/**
 * Where a parcel can be followed on its carrier's own page.
 *
 * The carrier is known by an id (Allegro's `INPOST`, `POCZTA_POLSKA`; Erli's
 * lower-case vendor name) and often by a name as well (`InPost Kurier`), so
 * both are read as words and the first carrier recognised wins. A carrier
 * Anvero has no page for (Allegro's own, `OTHER`, anything new) gets no link:
 * the number is still shown, as text.
 *
 * The addresses are the carriers' public tracking pages and were not opened
 * with a real number when written (`DECISIONS.md`); a carrier that moves its
 * page is a one-line change here.
 */
const TRACKING_PAGES: { words: string[]; url: (waybill: string) => string }[] = [
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
    const page = TRACKING_PAGES.find((candidate) =>
      candidate.words.some((word) => words.includes(word)),
    );
    if (page) return page.url(encodeURIComponent(number));
  }
  return null;
}
