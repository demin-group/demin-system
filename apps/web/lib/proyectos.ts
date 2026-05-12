export type Proyecto = {
  slug: string;
  calle: string;
  barrio: string;
  anio: number;
  fotos: string[];
};

export const proyectos: Proyecto[] = [
  { slug: "santa-engracia", calle: "Santa Engracia", barrio: "Almagro", anio: 2024, fotos: ["01.jpeg"] },
  { slug: "alberto-alcocer", calle: "Alberto Alcocer", barrio: "Nueva España", anio: 2025, fotos: ["01.jpeg", "02.jpeg"] },
  { slug: "nunez-de-balboa", calle: "Núñez de Balboa", barrio: "Salamanca", anio: 2025, fotos: ["01.jpeg", "02.jpeg"] },
  { slug: "nuevos-ministerios", calle: "Nuevos Ministerios", barrio: "Chamberí", anio: 2026, fotos: ["01.jpeg", "02.jpeg", "03.jpeg"] },
  { slug: "padre-damian", calle: "Padre Damián", barrio: "Nueva España", anio: 2026, fotos: ["01.jpeg", "02.jpeg"] },
  { slug: "santo-domingo-de-silos", calle: "Santo Domingo de Silos", barrio: "Pío XII", anio: 2026, fotos: ["01.jpeg", "02.jpeg", "03.jpeg"] },
];
