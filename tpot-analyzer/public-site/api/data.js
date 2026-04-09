const { serveBlobJson } = require("./_blobSiteData");

module.exports = async function handler(req, res) {
  return serveBlobJson(req, res, "data");
};
