// buckaroo-js-core has no `types` field in its package.json on this branch.
// tsconfig `paths` points the bare import at the real d.ts; this just
// silences the CSS side-effect import.
declare module "buckaroo-js-core/dist/style.css";
