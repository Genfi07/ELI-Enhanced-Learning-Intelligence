import {
  Search,
  FileText,
  Scale,
  Link2,
  Calculator,
  Lightbulb,
  type LucideIcon,
} from "lucide-react";

export interface Flow {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  accent: string;
  prompt: string;
  hint?: string;
}

export const FLOWS: Flow[] = [
  {
    id: "research",
    title: "Investigar un tema",
    description:
      "Busca en la web, lee las fuentes más relevantes y te da un resumen con puntos clave.",
    icon: Search,
    accent: "text-cyan-400",
    prompt: "Investiga a fondo sobre: ",
    hint: "el impacto de la IA en educación",
  },
  {
    id: "analyze-doc",
    title: "Analizar un documento",
    description:
      "Sube un PDF, Word o imagen y pídele que lo resuma, extraiga datos o busque algo concreto.",
    icon: FileText,
    accent: "text-emerald-400",
    prompt: "Analiza el documento que acabo de subir y dime: ",
    hint: "los puntos clave y conclusiones",
  },
  {
    id: "compare",
    title: "Comparar dos opciones",
    description:
      "Investiga ambas, contrasta ventajas y desventajas, y te da una tabla comparativa.",
    icon: Scale,
    accent: "text-violet-400",
    prompt:
      "Compara las siguientes dos opciones en cuanto a pros, contras y recomendación final:\n\nOpción A: \nOpción B: ",
    hint: "React vs Vue",
  },
  {
    id: "extract-url",
    title: "Extraer datos de una URL",
    description:
      "Lee una página web y extrae exactamente los datos que le pidas, en formato estructurado.",
    icon: Link2,
    accent: "text-blue-400",
    prompt:
      "Lee esta URL y extrae los siguientes datos en formato tabla:\n\nURL: \nDatos a extraer: ",
    hint: "https://… → precio, autor, fecha",
  },
  {
    id: "calculate",
    title: "Calcular paso a paso",
    description:
      "Resuelve operaciones, conversiones y cálculos mostrándote cada paso.",
    icon: Calculator,
    accent: "text-amber-400",
    prompt: "Calcula paso a paso y explícame cada operación: ",
    hint: "12.500 € al 4,5% anual durante 7 años",
  },
  {
    id: "explain",
    title: "Explicar algo difícil",
    description:
      "Convierte un tema complejo en algo claro, con ejemplos y analogías.",
    icon: Lightbulb,
    accent: "text-indigo-400",
    prompt:
      "Explícame de forma clara, con ejemplos y analogías, lo siguiente: ",
    hint: "consistencia eventual en sistemas distribuidos",
  },
];