/** The Annos mark: a faceted capital A — Panu's annos_logo.svg with the
 * Inkscape cruft stripped, otherwise the drawing as drawn: white paper,
 * gray facets, black hairlines, in both themes. It is a printed mark, not
 * a themed icon, so dark mode does not restyle it. */
export function AnnosMark({ className }: { className?: string }) {
  const stroke = {
    stroke: "#000000",
    strokeWidth: 0.5,
  } as const;
  return (
    <svg
      viewBox="17.4 25.6 165.2 148.7"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      className={className}
    >
      <g transform="translate(-3.1874932,-53.722916)" strokeLinejoin="round">
        {/* the gray arch — the A itself */}
        <path
          d="M 103.1875,79.639583 169.59792,227.80625 H 148.43125 L 103.1875,125.67708 58.208333,227.80625 h -21.43125 z"
          fill="#b3b3b3"
          {...stroke}
        />
        <path
          d="m 122.36979,168.67188 h 26.45833 l 6.74688,-10.45105 -21.29896,-9.39271 z"
          fill="#b3b3b3"
          {...stroke}
        />
        <path
          d="m 185.47292,227.80625 -22.225,-14.2875 -14.81667,14.2875 z"
          fill="#b3b3b3"
          {...stroke}
        />
        <path
          d="m 55.827083,185.20833 14.552084,14.81667 65.616663,3e-5 14.55209,-14.81667 z"
          fill="#b3b3b3"
          {...stroke}
        />
        {/* the paper facets */}
        <path
          d="M 155.575,158.22083 121.97291,79.639583 H 103.1875 l 30.95625,69.320837 z"
          fill="#ffffff"
          {...stroke}
        />
        <path
          d="m 185.47292,227.80625 -25.4,-59.26667 -75.93542,0.26459 -28.310417,16.40416 h 94.720837 l 12.7,28.31042 z"
          fill="#ffffff"
          {...stroke}
        />
        <path
          d="m 20.902084,227.80624 63.5,-148.166657 H 103.1875 L 36.777084,227.80624 Z"
          fill="#ffffff"
          {...stroke}
        />
        {/* the apex crease */}
        <path d="m 103.1875,79.639583 v 46.037497" fill="none" {...stroke} />
      </g>
    </svg>
  );
}
