/**
 * Save a file fetched with the login token under the given name, the same way `openPdf` opens
 * one in a tab: a plain `<a>` element does the actual save, since a login token cannot go on a
 * plain link's `href` for the browser to fetch on its own.
 */
export async function downloadFile(fetchFile: () => Promise<Blob>, filename: string): Promise<void> {
  const url = URL.createObjectURL(await fetchFile());
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
