export interface ImageRef {
  registry: string;
  namespace: string;
  name: string;
  tag: string;
  digest: string | null;
  raw: string;
}

export interface ImageResult {
  service: string;
  image: string;
  registry: string;
  repo: string | null;
  tag: string;
  commit: string | null;
  commit_url: string | null;
  status: string;
  resolution_method: string | null;
  confidence: string | null;
  matched_tag: string | null;
  steps: string[];
}
