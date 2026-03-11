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
  convertedKind?: "pdf" | "other";
  error?: string;
  fullExtraction: ExtractionFlags;
};

export type PenType = "tesseract" | "describe" | "graph";

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
};

export type ConversionResult = {
  source: string;
  converted?: string;
  kind: string;
  error?: string;
};
