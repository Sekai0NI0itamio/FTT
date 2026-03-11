export type FileKind = "pdf" | "image" | "docx" | "pptx" | "xlsx" | "other";

export type ExtractionFlags = {
  tesseract: boolean;
  python: boolean;
};

export type SourceFile = {
  id: string;
  path: string;
  name: string;
  kind: FileKind;
  selected: boolean;
  convertedPath?: string;
  convertedKind?: "pdf" | "image" | "other";
  error?: string;
  fullExtraction: ExtractionFlags;
};

export type PenType = "tesseract" | "describe" | "graph";

export type ChartModelInfo = {
  id: string;
  label: string;
  description: string;
  strengths: string[];
  weaknesses: string[];
};

export const CHART_MODELS: ChartModelInfo[] = [
  {
    id: "unichart",
    label: "UniChart",
    description: "State-of-the-art chart comprehension and data table extraction",
    strengths: [
      "Best at extracting raw data tables from charts",
      "Handles bar charts, line charts, and pie charts well",
      "Supports chart summarization and chart QA tasks",
    ],
    weaknesses: [
      "Slower inference due to VisionEncoderDecoder architecture",
      "Less accurate on scatter plots with dense overlapping points",
      "Struggles with 3D charts and perspective distortion",
    ],
  },
  {
    id: "matcha",
    label: "MatCha-ChartQA",
    description: "Enhanced chart understanding with math reasoning pretraining",
    strengths: [
      "Strong at answering numeric questions about charts",
      "Good with line graphs and trend analysis",
      "Fast inference (Pix2Struct architecture)",
    ],
    weaknesses: [
      "Outputs answers rather than full data tables",
      "Less suitable for raw data extraction tasks",
      "Can miss small annotations and legend entries",
    ],
  },
  {
    id: "deplot",
    label: "DePlot",
    description: "Plot-to-table translation (lightweight baseline)",
    strengths: [
      "Lightweight and fast to load and run",
      "Decent at simple bar and line charts",
      "Good default for initial extraction attempts",
    ],
    weaknesses: [
      "Lowest accuracy of the three models",
      "Often misreads values on complex multi-series charts",
      "Poor at stacked charts and area charts",
    ],
  },
];

export type Point = { x: number; y: number };

export type Stroke = {
  id: string;
  fileId: string;
  pageIndex: number;
  pen: PenType;
  points: Point[];
  radiusPx: number;
  unit: "px" | "cm" | "mm";
  filled: boolean;
  bbox: { x: number; y: number; width: number; height: number };
  /** Which graph models to use for this region (graph pen only). */
  graphModels?: string[];
};

export type ConversionResult = {
  source: string;
  converted?: string;
  kind: string;
  error?: string;
};
