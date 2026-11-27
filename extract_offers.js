// Collects the offers a product page publishes for search engines (schema.org JSON-LD or microdata).
// Returns a list of { price, currency, availability, seller }. The price is left as raw text,
// Python parses it.
() => {
  const offers = [];

  const walk = (node) => {
    if (Array.isArray(node)) return node.forEach(walk);
    if (!node || typeof node !== "object") return;
    const types = [].concat(node["@type"] || []);
    if ((types.includes("Offer") || types.includes("AggregateOffer")) && node.availability) {
      offers.push({
        price: String(node.price ?? node.lowPrice ?? ""),
        currency: String(node.priceCurrency || ""),
        availability: String(node.availability),
        seller: (node.seller && node.seller.name) || "",
      });
    }
    Object.values(node).forEach(walk);
  };
  document.querySelectorAll('script[type="application/ld+json"]').forEach((script) => {
    try {
      walk(JSON.parse(script.textContent));
    } catch (error) {
      // Some shops ship broken JSON-LD blocks, the other blocks are still worth reading.
    }
  });

  document.querySelectorAll('[itemtype*="schema.org/Offer"]').forEach((element) => {
    const read = (prop) => {
      const found = element.querySelector(`[itemprop="${prop}"]`);
      if (!found) return "";
      return found.getAttribute("content") || found.getAttribute("href") || found.textContent;
    };
    const availability = read("availability");
    if (availability) {
      offers.push({
        price: String(read("price")),
        currency: String(read("priceCurrency")),
        availability: availability,
        seller: "",
      });
    }
  });

  return offers;
}
