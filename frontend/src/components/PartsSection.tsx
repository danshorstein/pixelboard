type PurchasePart = {
  name: string;
  quantity: string;
  price: string;
  availability: string;
  availabilityTone?: "warning";
  description: string;
  image: string;
  imageAlt: string;
  href: string;
  source: string;
};

const purchaseParts: PurchasePart[] = [
  {
    name: "64×32 P4 HUB75 RGB matrix",
    quantity: "Qty 2",
    price: "$39.95 each",
    availability: "In stock when checked",
    description: "The two physical panels that join to create Pixelboard's 128×32 scoreboard face.",
    image: "https://cdn-shop.adafruit.com/970x728/2278-00.jpg",
    imageAlt: "A powered 64 by 32 P4 RGB LED matrix panel",
    href: "https://www.adafruit.com/product/2278",
    source: "Adafruit 2278"
  },
  {
    name: "Raspberry Pi 3 Model A+",
    quantity: "Qty 1",
    price: "$25.00",
    availability: "In stock when checked",
    description: "The compact Wi-Fi computer that fetches games and drives the display. Its GPIO header is preinstalled.",
    image: "https://cdn-shop.adafruit.com/970x728/4027-02.jpg",
    imageAlt: "Raspberry Pi 3 Model A Plus computer board",
    href: "https://www.adafruit.com/product/4027",
    source: "Adafruit 4027"
  },
  {
    name: "RGB Matrix Bonnet",
    quantity: "Qty 1",
    price: "$14.95 reference price",
    availability: "Adafruit out of stock · check DigiKey",
    availabilityTone: "warning",
    description: "Plugs onto the Pi and provides level shifting, the HUB75 socket, and protected panel power distribution.",
    image: "https://cdn-shop.adafruit.com/970x728/3211-08.jpg",
    imageAlt: "Adafruit RGB Matrix Bonnet driver board",
    href: "https://www.digikey.com/en/products/detail/adafruit-industries-llc/3211/8535237",
    source: "DigiKey · Adafruit 3211"
  },
  {
    name: "Regulated 5 V / 10 A panel supply",
    quantity: "Qty 1",
    price: "$29.95",
    availability: "In stock when checked",
    description: "A separate high-current supply for both LED panels. The panels must never be powered through the Pi.",
    image: "https://cdn-shop.adafruit.com/970x728/658-07.jpg",
    imageAlt: "Five volt ten amp enclosed switching power supply",
    href: "https://www.adafruit.com/product/658",
    source: "Adafruit 658"
  },
  {
    name: "5 V / 2.5 A Micro-USB Pi supply",
    quantity: "Qty 1",
    price: "$8.25",
    availability: "In stock when checked",
    description: "A stable, dedicated power supply for the Pi 3 A+. Keeping computer and panel power separate reduces surprises.",
    image: "https://cdn-shop.adafruit.com/970x728/1995-02.jpg",
    imageAlt: "Micro USB power supply for a Raspberry Pi",
    href: "https://www.adafruit.com/product/1995",
    source: "Adafruit 1995"
  },
  {
    name: "30 mm translucent arcade buttons",
    quantity: "Qty 2",
    price: "$5.95 each",
    availability: "In stock when checked",
    description: "Choose green for NEXT and blue for HOLD / WATCH LIVE. These are tactile, non-illuminated momentary switches.",
    image: "https://cdn-shop.adafruit.com/970x728/475-00.jpg",
    imageAlt: "Translucent green 30 millimeter arcade button",
    href: "https://www.adafruit.com/product/475",
    source: "Adafruit 475"
  },
  {
    name: "0.11-inch quick-connect wire pairs",
    quantity: "Qty 1 pack",
    price: "$4.95",
    availability: "In stock when checked",
    description: "Pre-crimped connectors that fit the plain arcade buttons and make the control wiring serviceable.",
    image: "https://cdn-shop.adafruit.com/970x728/1152-06.jpg",
    imageAlt: "Pack of quick-connect wire pairs for arcade buttons",
    href: "https://www.adafruit.com/product/1152",
    source: "Adafruit 1152"
  },
  {
    name: "M3 nylon screw and standoff set",
    quantity: "Qty 1 set",
    price: "$16.95",
    availability: "In stock when checked",
    description: "Nonconductive mounting hardware for the matrix panels and internal electronics.",
    image: "https://cdn-shop.adafruit.com/970x728/4685-01.jpg",
    imageAlt: "Open assortment box of black nylon M3 screws and standoffs",
    href: "https://www.adafruit.com/product/4685",
    source: "Adafruit 4685"
  }
];

const finishingParts = [
  {
    badge: "SD",
    name: "32–64 GB A2 microSD card",
    description: "Use a name-brand or official Raspberry Pi card. A2 or high-endurance media is preferred for a device that stays on.",
    href: "https://www.raspberrypi.com/products/sd-cards/?variant=sd-32gb",
    linkLabel: "Find an official Raspberry Pi SD card"
  },
  {
    badge: "GPIO",
    name: "Three-wire button harness",
    description: "Fabricate from 22–26 AWG stranded wire: BCM25 for NEXT, BCM19 for HOLD, plus one shared ground. Add insulated joints and strain relief.",
    href: "https://www.adafruit.com/product/3175",
    linkLabel: "See suitable 22 AWG stranded wire"
  },
  {
    badge: "CASE",
    name: "Ventilated matte enclosure",
    description: "Fabricate only after measuring the delivered panels. Include a removable service panel, airflow, strain relief, and room around the Wi-Fi antenna.",
    href: "https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/matrix-setup",
    linkLabel: "Review the panel setup guide"
  }
];

export function PartsSection() {
  return (
    <section className="parts-section" id="parts" aria-labelledby="parts-title">
      <header className="parts-heading">
        <div>
          <span className="eyebrow">Pixelboard Edition · pilot hardware</span>
          <h2 id="parts-title">Everything needed to build the scoreboard</h2>
          <p>
            This is the recommended low-surprise Pi 3 A+ build. The core electronics total is
            approximately <strong>$174.90</strong> before the microSD card, mounting hardware,
            enclosure, shipping, and tax.
          </p>
        </div>
        <div className="parts-spec" aria-label="Finished display dimensions">
          <span>Finished display</span>
          <strong>510 × 127 mm</strong>
          <small>128 × 32 pixels · two P4 panels</small>
        </div>
      </header>

      <div className="parts-grid">
        {purchaseParts.map((part) => (
          <article className="part-card" key={part.name}>
            <a
              className="part-image-link"
              href={part.href}
              target="_blank"
              rel="noreferrer"
              aria-label={`View ${part.name} from ${part.source}`}
            >
              <img src={part.image} alt={part.imageAlt} loading="lazy" decoding="async" />
              <span className="part-quantity">{part.quantity}</span>
            </a>
            <div className="part-copy">
              <h3>{part.name}</h3>
              <div className="part-purchase-meta">
                <strong>{part.price}</strong>
                <span className={part.availabilityTone === "warning" ? "stock-warning" : ""}>
                  {part.availability}
                </span>
              </div>
              <p>{part.description}</p>
              <a className="part-buy-link" href={part.href} target="_blank" rel="noreferrer">
                View {part.source} <span aria-hidden="true">↗</span>
              </a>
            </div>
          </article>
        ))}
      </div>

      <div className="finishing-block">
        <div className="finishing-intro">
          <span className="eyebrow">Source or fabricate locally</span>
          <h3>Three finishing items</h3>
          <p>These depend on the final enclosure and how you want to use the unit.</p>
        </div>
        <div className="finishing-grid">
          {finishingParts.map((part) => (
            <article className="finishing-card" key={part.name}>
              <span className="finishing-badge" aria-hidden="true">{part.badge}</span>
              <div>
                <h4>{part.name}</h4>
                <p>{part.description}</p>
                <a href={part.href} target="_blank" rel="noreferrer">
                  {part.linkLabel} <span aria-hidden="true">↗</span>
                </a>
              </div>
            </article>
          ))}
        </div>
      </div>

      <aside className="power-warning" aria-label="Important power safety note">
        <span aria-hidden="true">!</span>
        <p>
          <strong>Power rule:</strong> use separate regulated supplies for the Pi and LED panels.
          Never feed panel power through the Pi, and never use thin breadboard wires for the
          panel-current path. An adult should own mains wiring, high-current connections, and the
          final enclosure inspection.
        </p>
      </aside>

      <p className="parts-attribution">
        Prices and availability checked July 16, 2026 and may change. Product photos are served by
        Adafruit and link to the corresponding supplier listing; no supplier endorsement is implied.
        This is an unofficial personal prototype and is not affiliated with or endorsed by MLB or
        any club. MLB and club marks belong to their respective owners.
      </p>
    </section>
  );
}
