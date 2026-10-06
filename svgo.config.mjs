// svgo.config.mjs — aggressive, but not at the cost of the design.
//
// Two things in these SVGs are load-bearing and svgo's default preset eats them:
//
//   * `<line>` and `<circle>` start at `opacity="0"` because SMIL reveals them.
//     That looks exactly like a hidden element, so `removeHiddenElems` deletes
//     the stylus and the "now" marker together with their animations. Measured:
//     default preset went 4 animation nodes -> 1 and 1 `<line>` -> 0.
//   * `<use href="#…">` into a shared glyph atlas is the whole typography
//     strategy. `cleanupIds` is *safe* (it rewrites every reference — 307/307
//     survived) and keeps ids short, so it stays on.
//
// The CSS morph needs three more plugins off; see the overrides below.
//
// Everything else is preset-default with multipass, plus `sortAttrs`, which
// pays for itself here because the same attribute names repeat across hundreds
// of adjacent `<use>` elements.
//
// `convertShapeToPath` had to go as well, and this one is subtle: the activity
// trace is revealed by a clip `<rect width="0">` that SMIL animates to its full
// width. Converted to `<path d="M248 162v104z">` the clip becomes a zero-area
// path, `attributeName="width"` then targets an attribute paths do not have, and
// the whole trace disappears while every screenshot still looks plausible - only
// the "now" marker sits outside the clip and survives. Measured effect: 101
// paths in, 0 visible trace out. `verify.py` now checks that every `<animate>`
// owns the attribute it drives, so this class of bug cannot pass the gate again.
export default {
  multipass: true,
  js2svg: { pretty: false },
  plugins: [
    {
      name: 'preset-default',
      params: {
        overrides: {
          removeHiddenElems: false,
          convertShapeToPath: false,
          // A screen reader gets <title>/<desc> out of an SVG used as an image.
          // (svgo 4 no longer runs removeTitle/removeViewBox in the preset, so
          // only removeDesc still needs switching off.)
          removeDesc: false,
          // The face <-> logo morph animates `transform` from CSS on each
          // traveller dot. These three would push the group's transform (and
          // its class) down onto every dot, where the CSS transform then
          // overwrites it and the dots land at the origin, unscaled.
          collapseGroups: false,
          moveGroupAttrsToElems: false,
          inlineStyles: false,
        },
      },
    },
    'sortAttrs',
  ],
};
