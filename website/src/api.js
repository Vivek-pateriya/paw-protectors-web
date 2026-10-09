export async function request(path, token, method = "GET", data, signal) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {},
    options = { method, headers, signal };
  if (data instanceof FormData) options.body = data;
  else if (data !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(data);
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = `HTTP ${response.status}`;
    }
    const error = new Error(
      Array.isArray(detail)
        ? detail.map((d) => `${d.loc?.slice(1).join(" ")}: ${d.msg}`).join("; ")
        : typeof detail === "string"
          ? detail
          : "Request failed",
    );
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
