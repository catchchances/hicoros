const form = document.getElementById("convertForm");
const status = document.getElementById("status");
const submitBtn = document.getElementById("submitBtn");
const apiBaseUrl = (window.HICOROS_API_BASE_URL || "").replace(/\/$/, "");
const convertApiUrl = apiBaseUrl ? `${apiBaseUrl}/api/convert` : "./api/convert";

function setStatus(text, isError = false) {
  status.textContent = text;
  status.style.color = isError ? "#b00020" : "#222";
}

function getFilenameFromDisposition(disposition) {
  if (!disposition) return null;
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || null;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const formData = new FormData(form);
  const file = formData.get("sourceFile");
  if (!(file instanceof File) || file.size === 0) {
    setStatus("请选择要上传的 JSON 或 ZIP 文件。", true);
    return;
  }

  submitBtn.disabled = true;
  setStatus("转换中，请稍候...");

  try {
    const response = await fetch(convertApiUrl, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      let message = `请求失败：${response.status}`;
      try {
        const data = await response.json();
        if (data?.error) {
          message = `${data.error}${data.detail ? `\n${data.detail}` : ""}`;
        }
      } catch {
        // ignore json parse errors
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition");
    const filename = getFilenameFromDisposition(disposition) || "result.fit";

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    setStatus("转换成功，已开始下载文件。\n如果浏览器拦截下载，请手动允许。", false);
  } catch (error) {
    setStatus(`转换失败：\n${error.message || error}`, true);
  } finally {
    submitBtn.disabled = false;
  }
});
