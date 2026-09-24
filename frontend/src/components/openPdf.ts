/**
 * Show a PDF fetched with the login token in a new tab.
 *
 * The tab is opened before the request, while the click is still the
 * browser's "user gesture", so it is not blocked as a pop-up; it is closed
 * again if the request fails, and the error is thrown on.
 */
export async function openPdf(fetchPdf: () => Promise<Blob>): Promise<void> {
  const tab = window.open("", "_blank");
  try {
    const url = URL.createObjectURL(await fetchPdf());
    if (tab) tab.location.href = url;
    else window.location.assign(url);
  } catch (err) {
    tab?.close();
    throw err;
  }
}
