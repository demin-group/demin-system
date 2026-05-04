const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://demingroupmadrid.com";

export default function LocalBusinessJsonLd() {
  const data = {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: "DEMIN Group",
    image: `${SITE_URL}/logo-demin.jpg`,
    "@id": SITE_URL,
    url: SITE_URL,
    telephone: "+34692319217",
    address: {
      "@type": "PostalAddress",
      streetAddress: "C/ de Alfonso X, 5",
      addressLocality: "Madrid",
      postalCode: "28010",
      addressCountry: "ES",
    },
    areaServed: { "@type": "City", name: "Madrid" },
    sameAs: [
      "https://www.instagram.com/demin.group/",
      "https://www.linkedin.com/company/demin-group/",
    ],
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
