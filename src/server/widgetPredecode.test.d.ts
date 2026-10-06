/**
 * The Jupyter widget (packages/js/widget.tsx) decodes ``df_data_dict`` before
 * it renders. Decoding is async, so a slow decode of an older dict can finish
 * after a newer one and must not be rendered over it (#1046).
 *
 * Decodes are held open here so the test chooses the order they finish in.
 */
export {};
