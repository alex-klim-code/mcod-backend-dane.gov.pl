/**
 * Backend-only client. Node.js 20+ built-in fetch/FormData/Blob.
 * Never import this module into the browser.
 */
export type ResourceStatus = {
  resource_id: number;
  dataset_id: number;
  status: string;
  file_validation: string;
  data_validation: string;
  link_validation: string;
  metadata_url: string | null;
  file_url: string | null;
};

export class McodError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export class McodAedClient {
  private base: URL;
  constructor(baseUrl: string, private secret: string) {
    this.base = new URL(baseUrl.replace(/\/?$/, "/"));
    if (this.base.protocol !== "https:" || !secret) {
      throw new Error("HTTPS MCOD_API_BASE_URL and a server-side integration secret are required.");
    }
  }

  private async request<T>(path: string, method = "GET", body?: BodyInit): Promise<T> {
    const url = new URL(path.replace(/^\//, ""), this.base);
    if (url.origin !== this.base.origin) throw new Error("Unexpected MCOD origin.");
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.secret}`,
      Accept: "application/json",
    };
    if (typeof body === "string") headers["Content-Type"] = "application/json";
    const response = await fetch(url, {
      method, body, headers,
      redirect: "error",
      signal: AbortSignal.timeout(60_000),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new McodError(
        response.status,
        result.error?.code ?? "mcod_error",
        result.error?.message ?? `MCOD returned HTTP ${response.status}`,
      );
    }
    return result as T;
  }

  private org(id: string) {
    return `integrations/aed/v1/organizations/${encodeURIComponent(id)}`;
  }
  institutions() {
    return this.request<{ data: unknown[] }>("integrations/aed/v1/institutions");
  }
  datasets(org: string) {
    return this.request<{ data: unknown[] }>(`${this.org(org)}/datasets`);
  }
  createDataset(org: string, data: {
    external_dataset_id: string; title: string; description: string;
    source_url: string; license: string; mcod_dataset_id?: number;
  }) {
    return this.request<{ dataset_id: number; status: string }>(
      `${this.org(org)}/datasets`, "POST", JSON.stringify(data),
    );
  }
  dataset(org: string, id: string) {
    return this.request<{ dataset_id: number; resources: ResourceStatus[] }>(
      `${this.org(org)}/datasets/${encodeURIComponent(id)}`,
    );
  }
  publishDataset(org: string, id: string) {
    return this.request(`${this.org(org)}/datasets/${encodeURIComponent(id)}/publish`, "POST");
  }
  uploadResource(org: string, dataset: string, title: string, filename: string,
    bytes: Uint8Array, resourceId?: number) {
    const form = new FormData();
    form.set("external_dataset_id", dataset);
    form.set("title", title);
    form.set("file", new Blob([bytes]), filename);
    const path = resourceId === undefined
      ? `${this.org(org)}/datasets/${encodeURIComponent(dataset)}/resources`
      : `${this.org(org)}/resources/${resourceId}`;
    return this.request<ResourceStatus>(path, resourceId === undefined ? "POST" : "PUT", form);
  }
  resource(org: string, id: number) {
    return this.request<ResourceStatus>(`${this.org(org)}/resources/${id}`);
  }
  publishResource(org: string, id: number) {
    return this.request<ResourceStatus>(`${this.org(org)}/resources/${id}/publish`, "POST");
  }
  aggregate(rebuild = false) {
    return this.request<{
      status: string; record_count?: number; last_error?: string | null;
      resource_id?: number; file_url?: string | null;
    }>("integrations/aed/v1/aggregate", rebuild ? "POST" : "GET");
  }
}
