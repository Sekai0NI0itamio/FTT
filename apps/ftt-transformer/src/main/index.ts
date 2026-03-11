import { app, BrowserWindow, dialog, ipcMain } from "electron";
import path from "node:path";
import fs from "node:fs";
import { promises as fsp } from "node:fs";
import { spawn } from "node:child_process";
import { PDFDocument } from "pdf-lib";
import archiver from "archiver";

const WORK_DIR_NAME = "ftt-transformer";

const devServerUrl = process.env.VITE_DEV_SERVER_URL || "http://localhost:5173/";

const ensureDir = async (dir: string) => {
  await fsp.mkdir(dir, { recursive: true });
};

const getWorkRoot = () => {
  const root = path.join(app.getPath("userData"), WORK_DIR_NAME);
  return root;
};

const copyFile = async (src: string, dest: string) => {
  await ensureDir(path.dirname(dest));
  await fsp.copyFile(src, dest);
};

const runCommand = (cmd: string, args: string[]) =>
  new Promise<void>((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: "ignore" });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${cmd} exited with ${code}`));
    });
  });

const convertOfficeToPdf = async (inputPath: string, outputDir: string) => {
  const commands = ["soffice", "libreoffice"];
  for (const command of commands) {
    try {
      await runCommand(command, [
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        outputDir,
        inputPath,
      ]);
      const expected = path.join(outputDir, `${path.parse(inputPath).name}.pdf`);
      if (fs.existsSync(expected)) return expected;
    } catch {
      // Try next command
    }
  }
  throw new Error("LibreOffice not available for conversion");
};

const convertImageToPdf = async (inputPath: string, outputPath: string) => {
  const bytes = await fsp.readFile(inputPath);
  const pdfDoc = await PDFDocument.create();
  const image = inputPath.toLowerCase().endsWith(".png")
    ? await pdfDoc.embedPng(bytes)
    : await pdfDoc.embedJpg(bytes);
  const page = pdfDoc.addPage([image.width, image.height]);
  page.drawImage(image, { x: 0, y: 0, width: image.width, height: image.height });
  const pdfBytes = await pdfDoc.save();
  await ensureDir(path.dirname(outputPath));
  await fsp.writeFile(outputPath, pdfBytes);
};

const normalizeFileKind = (filePath: string) => {
  const ext = path.extname(filePath).toLowerCase();
  if ([".pdf"].includes(ext)) return "pdf";
  if ([".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"].includes(ext)) return "image";
  if ([".docx"].includes(ext)) return "docx";
  if ([".pptx"].includes(ext)) return "pptx";
  if ([".xlsx"].includes(ext)) return "xlsx";
  return "other";
};

const convertFile = async (filePath: string, outputDir: string) => {
  const kind = normalizeFileKind(filePath);
  const baseName = path.parse(filePath).name;
  if (kind === "pdf") {
    const target = path.join(outputDir, `${baseName}.pdf`);
    await copyFile(filePath, target);
    return { kind: "pdf", path: target };
  }
  if (kind === "image") {
    const target = path.join(outputDir, `${baseName}.pdf`);
    await convertImageToPdf(filePath, target);
    return { kind: "pdf", path: target };
  }
  if (["docx", "pptx", "xlsx"].includes(kind)) {
    const target = await convertOfficeToPdf(filePath, outputDir);
    return { kind: "pdf", path: target };
  }
  return { kind: "other", path: filePath };
};

const createWindow = () => {
  const mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1200,
    minHeight: 800,
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      sandbox: true,
      contextIsolation: true,
    },
  });

  if (!app.isPackaged) {
    mainWindow.loadURL(devServerUrl);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
};

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("ftt:select-files", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openFile", "multiSelections"],
  });
  return result.canceled ? [] : result.filePaths;
});

ipcMain.handle("ftt:select-folder", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory", "createDirectory"],
  });
  return result.canceled ? "" : result.filePaths[0];
});

ipcMain.handle("ftt:read-file", async (_event, payload) => {
  const { filePath } = payload as { filePath: string };
  const buffer = await fsp.readFile(filePath);
  return buffer;
});

ipcMain.handle("ftt:convert-files", async (event, payload) => {
  const { requestId, files } = payload as { requestId: string; files: string[] };
  const workRoot = getWorkRoot();
  const outputDir = path.join(workRoot, "converted");
  await ensureDir(outputDir);

  const results: Array<{ source: string; converted?: string; kind: string; error?: string }> = [];
  let index = 0;
  for (const filePath of files) {
    index += 1;
    try {
      const converted = await convertFile(filePath, outputDir);
      results.push({ source: filePath, converted: converted.path, kind: converted.kind });
      event.sender.send("ftt:convert-progress", {
        requestId,
        current: index,
        total: files.length,
        file: filePath,
        status: "ok",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Conversion failed";
      results.push({ source: filePath, kind: "error", error: message });
      event.sender.send("ftt:convert-progress", {
        requestId,
        current: index,
        total: files.length,
        file: filePath,
        status: "error",
        error: message,
      });
    }
  }
  return results;
});

ipcMain.handle("ftt:save-project", async (_event, payload) => {
  const { project, targetDir, includeUploads } = payload as {
    project: Record<string, unknown>;
    targetDir: string;
    includeUploads: boolean;
  };
  await ensureDir(targetDir);
  const projectPath = path.join(targetDir, "project.json");
  await fsp.writeFile(projectPath, JSON.stringify(project, null, 2));
  if (includeUploads && project && typeof project === "object") {
    const uploads = (project as { uploads?: string[] }).uploads || [];
    const uploadsDir = path.join(targetDir, "uploads");
    await ensureDir(uploadsDir);
    for (const filePath of uploads) {
      const dest = path.join(uploadsDir, path.basename(filePath));
      await copyFile(filePath, dest);
    }
  }
  return projectPath;
});

ipcMain.handle("ftt:export-project", async (_event, payload) => {
  const { project, regions, targetZip } = payload as {
    project: Record<string, unknown>;
    regions: Array<{ pen: string; name: string; dataUrl: string }>;
    targetZip: string;
  };

  const workRoot = getWorkRoot();
  const exportDir = path.join(workRoot, `export-${Date.now()}`);
  await ensureDir(exportDir);

  /* ── regions/ grouped by pen type ─────────────────────── */
  const regionsDir = path.join(exportDir, "regions");
  await ensureDir(regionsDir);

  for (const region of regions) {
    if (!region.dataUrl) continue;
    const penDir = path.join(regionsDir, region.pen);
    await ensureDir(penDir);
    const base64 = region.dataUrl.split(",")[1] || "";
    const buffer = Buffer.from(base64, "base64");
    await fsp.writeFile(path.join(penDir, region.name), buffer);
  }

  /* ── uploads/ with converted PDFs and source files ────── */
  const uploadsDir = path.join(exportDir, "uploads");
  await ensureDir(uploadsDir);

  const files = (project as { files?: Array<{ path: string; convertedPath: string; name: string }> }).files || [];
  for (const file of files) {
    if (file.convertedPath && fs.existsSync(file.convertedPath)) {
      const dest = path.join(uploadsDir, path.basename(file.convertedPath));
      await copyFile(file.convertedPath, dest);
    }
    if (file.path && fs.existsSync(file.path)) {
      const dest = path.join(uploadsDir, path.basename(file.path));
      if (!fs.existsSync(dest)) {
        await copyFile(file.path, dest);
      }
    }
  }

  /* ── project.json ─────────────────────────────────────── */
  const projectPath = path.join(exportDir, "project.json");
  await fsp.writeFile(projectPath, JSON.stringify(project, null, 2));

  /* ── status.tag — extraction tags per file ────────────── */
  const statusLines: string[] = ["# FTT Transformer — Status Tags", ""];
  const allFiles = (project as { files?: Array<{ name: string; fullExtraction?: { tesseract?: boolean; python?: boolean } }> }).files || [];
  for (const file of allFiles) {
    const tags: string[] = [];
    if (file.fullExtraction?.tesseract) tags.push("tesseract");
    if (file.fullExtraction?.python) tags.push("python");
    statusLines.push(`${file.name}: ${tags.join(", ") || "none"}`);
  }
  statusLines.push("");
  await fsp.writeFile(path.join(exportDir, "status.tag"), statusLines.join("\n"));

  /* ── zip everything ───────────────────────────────────── */
  await new Promise<void>((resolve, reject) => {
    const output = fs.createWriteStream(targetZip);
    const archive = archiver("zip", { zlib: { level: 9 } });
    output.on("close", () => resolve());
    archive.on("error", (err) => reject(err));
    archive.pipe(output);
    archive.directory(exportDir, false);
    archive.finalize();
  });

  return targetZip;
});
