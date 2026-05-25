"use client";

function parentDirectory(relativePath: string) {
  const cleaned = relativePath.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
  if (!cleaned.includes("/")) {
    return "";
  }
  return cleaned.split("/").slice(0, -1).join("/");
}

export function sourceFolderBrowseHref(sourceId: string, relativePath: string) {
  const folderPath = parentDirectory(relativePath);
  return folderPath ? `/sources/${sourceId}?path=${encodeURIComponent(folderPath)}` : `/sources/${sourceId}`;
}
