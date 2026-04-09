export const DATA_JSON_ENDPOINT = '/api/data'
export const SEARCH_JSON_ENDPOINT = '/api/search'

export async function fetchJson(endpoint) {
  const response = await fetch(endpoint)
  if (!response.ok) {
    throw new Error(`Failed to load ${endpoint}: ${response.status} ${response.statusText}`)
  }
  return response.json()
}
