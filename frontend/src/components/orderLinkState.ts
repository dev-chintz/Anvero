/**
 * What a link to an order carries in its router state, so the order's own page
 * knows where it was opened from. Both parts are optional: an order opened
 * from a bookmark or another page has neither, and the page still works.
 */
export interface OrderLinkState {
  /** Where "back" goes: the list, with its filters and page in the query string. */
  closeTo?: string;
  /** The orders of the list the link was in, in its order: what the next and previous arrows walk. */
  orderIds?: string[];
}
