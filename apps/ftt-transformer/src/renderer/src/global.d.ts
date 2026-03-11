export {};

declare global {
  interface Window {
    ftt?: {
      selectFiles: () => Promise<string[]>;
      selectFolder: () => Promise<string>;
      readFile: (filePath: string) => Promise<ArrayBuffer>;
      convertFiles: (payload: { requestId: string; files: string[] }) => Promise<unknown>;
      onConvertProgress: (handler: (event: unknown, payload: unknown) => void) => void;
      offConvertProgress?: (handler: (event: unknown, payload: unknown) => void) => void;
      saveProject: (payload: { project: Record<string, unknown>; targetDir: string; includeUploads: boolean }) => Promise<string>;
      exportProject: (payload: {
        project: Record<string, unknown>;
        regions: Array<{ pen: string; name: string; dataUrl: string; graphModels?: string[] }>;
        targetZip: string;
      }) => Promise<string>;
    };
  }
}
