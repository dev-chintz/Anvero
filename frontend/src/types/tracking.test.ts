import { describe, expect, it } from "vitest";
import { trackingUrl } from "./tracking";

describe("trackingUrl", () => {
  it.each([
    [{ carrier_id: "INPOST" }, "https://inpost.pl/sledzenie-przesylek?number=6"],
    [{ carrier_id: "DPD" }, "https://tracktrace.dpd.com.pl/parcelDetails?p1=6"],
    [{ carrier_id: "DHL" }, "https://www.dhl.com/pl-pl/home/tracking.html?tracking-id=6"],
    [{ carrier_id: "POCZTA_POLSKA" }, "https://emonitoring.poczta-polska.pl/?numer=6"],
    [{ carrier_id: "UPS" }, "https://www.ups.com/track?loc=pl_PL&tracknum=6"],
    [{ carrier_id: "GLS" }, "https://gls-group.com/PL/pl/sledzenie-paczek?match=6"],
    [{ carrier_id: "FEDEX" }, "https://www.fedex.com/fedextrack/?trknbr=6"],
  ])("knows the page of %j", (carrier, expected) => {
    expect(trackingUrl(carrier, "6")).toBe(expected);
  });

  it("reads the carrier the way each marketplace spells it", () => {
    // Erli gives its vendor in lower case, Allegro an id and often a name
    expect(trackingUrl({ carrier_id: "inpost" }, "52100")).toContain("inpost.pl");
    expect(trackingUrl({ carrier_id: null, carrier_name: "InPost Kurier" }, "52100")).toContain(
      "inpost.pl",
    );
    expect(trackingUrl({ carrier_id: "OTHER", carrier_name: "DPD Polska" }, "52100")).toContain(
      "dpd.com.pl",
    );
  });

  it("reads the id before the name", () => {
    expect(trackingUrl({ carrier_id: "DHL", carrier_name: "InPost" }, "1")).toContain("dhl.com");
  });

  it("does not take a carrier for a word that merely contains its name", () => {
    expect(trackingUrl({ carrier_name: "Groups Express" }, "1")).toBeNull();
    expect(trackingUrl({ carrier_name: "Glossy" }, "1")).toBeNull();
  });

  it("offers nothing for a carrier it has no page for", () => {
    expect(trackingUrl({ carrier_id: "ALLEGRO" }, "1")).toBeNull();
    expect(trackingUrl({ carrier_id: "OTHER", carrier_name: "Kurier lokalny" }, "1")).toBeNull();
    expect(trackingUrl({}, "1")).toBeNull();
  });

  it("offers nothing without a number", () => {
    expect(trackingUrl({ carrier_id: "INPOST" }, "")).toBeNull();
    expect(trackingUrl({ carrier_id: "INPOST" }, "   ")).toBeNull();
    expect(trackingUrl({ carrier_id: "INPOST" }, null)).toBeNull();
  });

  it("keeps a number from breaking out of the address", () => {
    const url = trackingUrl({ carrier_id: "INPOST" }, " 12 34&x=1#z ");

    expect(url).toBe("https://inpost.pl/sledzenie-przesylek?number=12%2034%26x%3D1%23z");
  });
});
