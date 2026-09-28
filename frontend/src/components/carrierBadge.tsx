import { wordsOf } from "../types/tracking";
import allegroLogo from "../assets/carriers/allegro.svg";
import dhlLogo from "../assets/carriers/dhl.svg";
import dpdLogo from "../assets/carriers/dpd.svg";
import fedexLogo from "../assets/carriers/fedex.svg";
import upsLogo from "../assets/carriers/ups.svg";

/**
 * Puts a name and, where one is on hand, a real brand mark on the delivery
 * method Allegro or Erli reports (`delivery.method`, free text such as
 * "Kurier DPD" or "Allegro One Box, One Kurier") - so the operator sees the
 * carrier at a glance rather than reading the sentence. Matched the same way
 * as a shipment's tracking page (`types/tracking.ts`): by word, case-insensitively,
 * first candidate whose word appears anywhere in the text.
 *
 * The marks for DHL, DPD, UPS, FedEx and Allegro are Simple Icons' real SVGs
 * (MIT licensed, `frontend/src/assets/carriers/`), recoloured white to sit on
 * the brand's own colour. InPost, Poczta Polska and GLS have no icon in that
 * set, so their badge is the name alone on the brand's colour.
 */
interface CarrierBrand {
  words: string[];
  name: string;
  color: string;
  textColor: string;
  logo?: string;
}

const CARRIER_BRANDS: CarrierBrand[] = [
  { words: ["dpd"], name: "DPD", color: "#DC0032", textColor: "#fff", logo: dpdLogo },
  { words: ["dhl"], name: "DHL", color: "#D40511", textColor: "#fff", logo: dhlLogo },
  { words: ["ups"], name: "UPS", color: "#150400", textColor: "#fff", logo: upsLogo },
  { words: ["fedex"], name: "FedEx", color: "#4D148C", textColor: "#fff", logo: fedexLogo },
  { words: ["poczta", "pocztex"], name: "Poczta Polska", color: "#E4022B", textColor: "#fff" },
  { words: ["gls"], name: "GLS", color: "#FFB600", textColor: "#1a1a1a" },
  { words: ["inpost", "paczkomat", "paczkomaty"], name: "InPost", color: "#FFCB05", textColor: "#1a1a1a" },
  { words: ["allegro", "one"], name: "Allegro One", color: "#FF5A00", textColor: "#fff", logo: allegroLogo },
];

export function carrierBrand(deliveryMethod: string | null | undefined): CarrierBrand | null {
  const words = wordsOf(deliveryMethod);
  if (words.length === 0) return null;
  return CARRIER_BRANDS.find((brand) => brand.words.some((word) => words.includes(word))) ?? null;
}

export function CarrierBadge({ deliveryMethod }: { deliveryMethod: string | null | undefined }) {
  const brand = carrierBrand(deliveryMethod);
  if (!brand) return null;

  return (
    <span
      className="carrier-badge"
      style={{ background: brand.color, color: brand.textColor }}
    >
      {brand.logo && <img src={brand.logo} alt="" className="carrier-badge-logo" />}
      {brand.name}
    </span>
  );
}
