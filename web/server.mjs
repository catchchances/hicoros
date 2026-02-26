import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import os from "node:os";

import AdmZip from "adm-zip";
import express from "express";
import multer from "multer";

const app = express();
const port = process.env.PORT || 8080;

const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 100 * 1024 * 1024,
  },
});

app.use(express.static(path.resolve("./public")));

function runCommand(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", (error) => {
      reject(error);
    });

    child.on("close", (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        reject(new Error(`Command failed with code ${code}\n${stderr || stdout}`));
      }
    });
  });
}

async function listFitFiles(dir) {
  const files = await fs.readdir(dir, { withFileTypes: true });
  return files
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".fit"))
    .map((entry) => path.join(dir, entry.name));
}

app.post("/api/convert", upload.single("sourceFile"), async (req, res) => {
  let workDir;

  try {
    if (!req.file) {
      return res.status(400).json({ error: "未收到上传文件，请选择 JSON 或 ZIP。" });
    }

    const ext = path.extname(req.file.originalname).toLowerCase();
    if (ext !== ".json" && ext !== ".zip") {
      return res.status(400).json({ error: "仅支持 .json 或 .zip 文件。" });
    }

    workDir = await fs.mkdtemp(path.join(os.tmpdir(), "hicoros-web-"));
    const inputPath = path.join(workDir, `input${ext}`);
    const outputDir = path.join(workDir, "output");

    await fs.mkdir(outputDir, { recursive: true });
    await fs.writeFile(inputPath, req.file.buffer);

    const baseArgs = ["run", "hicoros", "--output_dir", outputDir];
    if (ext === ".zip") {
      baseArgs.push("--zip", inputPath);
    } else {
      baseArgs.push("--json", inputPath);
    }

    const sportsRaw = (req.body?.jsonSportFilter || "").trim();
    if (sportsRaw) {
      const sports = sportsRaw
        .split(/[\s,]+/)
        .map((value) => value.trim())
        .filter(Boolean);
      if (sports.length > 0) {
        baseArgs.push("--json_sport_filter", ...sports);
      }
    }

    await runCommand("uv", baseArgs);

    const fitFiles = await listFitFiles(outputDir);
    if (fitFiles.length === 0) {
      return res.status(500).json({ error: "转换完成，但未找到 FIT 输出文件。" });
    }

    if (fitFiles.length === 1) {
      const onlyFile = fitFiles[0];
      return res.download(onlyFile, path.basename(onlyFile));
    }

    const zip = new AdmZip();
    for (const fitFile of fitFiles) {
      zip.addLocalFile(fitFile);
    }

    const zipBuffer = zip.toBuffer();
    res.setHeader("Content-Type", "application/zip");
    res.setHeader("Content-Disposition", 'attachment; filename="converted-fit-files.zip"');
    return res.send(zipBuffer);
  } catch (error) {
    return res.status(500).json({
      error: "转换失败",
      detail: String(error.message || error),
    });
  } finally {
    if (workDir) {
      await fs.rm(workDir, { recursive: true, force: true });
    }
  }
});

app.get("/api/health", (_req, res) => {
  res.json({ ok: true });
});

app.listen(port, () => {
  console.log(`hicoros naive web server listening at http://localhost:${port}`);
});
