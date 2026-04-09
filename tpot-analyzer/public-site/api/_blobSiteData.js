const { get } = require("@vercel/blob");

const SITE_DATA_BLOB_PATHS = {
  data: "public-site/data.json",
  search: "public-site/search.json",
};

async function readBlobBuffer(pathname) {
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  if (!token) {
    const error = new Error("Missing BLOB_READ_WRITE_TOKEN for public-site blob reads");
    error.code = "config_error";
    throw error;
  }

  const blobResult = await get(pathname, {
    access: "public",
    token,
  });

  if (!blobResult || blobResult.statusCode !== 200 || !blobResult.stream) {
    return null;
  }

  const body = Buffer.from(await new Response(blobResult.stream).arrayBuffer());
  return {
    body,
    blob: blobResult.blob,
  };
}

async function serveBlobJson(req, res, kind) {
  if (req.method !== "GET") {
    return res.status(405).json({
      error: "Method not allowed",
      code: "method_not_allowed",
    });
  }

  const pathname = SITE_DATA_BLOB_PATHS[kind];
  if (!pathname) {
    return res.status(500).json({
      error: `Unknown site data blob kind: ${kind}`,
      code: "config_error",
    });
  }

  try {
    const blobPayload = await readBlobBuffer(pathname);
    if (!blobPayload) {
      return res.status(404).json({
        error: `Blob not found for ${kind}: ${pathname}`,
        code: "not_found",
      });
    }

    const { body, blob } = blobPayload;
    res.setHeader("Content-Type", blob.contentType || "application/json; charset=utf-8");
    res.setHeader("Cache-Control", blob.cacheControl || "public, max-age=300");
    res.setHeader("X-Public-Site-Blob-Path", blob.pathname);
    return res.status(200).send(body);
  } catch (error) {
    console.error(`[public-site:${kind}] Blob read failed`, {
      message: error?.message,
      code: error?.code,
      pathname,
    });
    return res.status(500).json({
      error: `Failed to load ${kind} blob data`,
      code: error?.code || "blob_read_failed",
      detail: error?.message || String(error),
    });
  }
}

module.exports = {
  SITE_DATA_BLOB_PATHS,
  serveBlobJson,
};
