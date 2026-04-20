const DB_NAME = "worldbox-writer";
const STORE_NAME = "drafts";

export interface EditorDraft {
  key: string;
  simId: string;
  branchId: string;
  nodeId: string;
  html: string;
  plainText: string;
  updatedAt: string;
}

function fallbackStorageKey(key: string) {
  return `worldbox:draft:${key}`;
}

function hasIndexedDb() {
  return typeof window !== "undefined" && "indexedDB" in window;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export function buildDraftKey(
  simId: string,
  branchId: string,
  nodeId: string
) {
  return `${simId}:${branchId}:${nodeId}`;
}

export async function loadDraft(key: string): Promise<EditorDraft | null> {
  if (!hasIndexedDb()) {
    const raw = window.localStorage.getItem(fallbackStorageKey(key));
    return raw ? (JSON.parse(raw) as EditorDraft) : null;
  }

  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const request = tx.objectStore(STORE_NAME).get(key);
    request.onsuccess = () => resolve((request.result as EditorDraft | undefined) ?? null);
    request.onerror = () => reject(request.error);
  });
}

export async function saveDraft(draft: EditorDraft): Promise<void> {
  if (!hasIndexedDb()) {
    window.localStorage.setItem(
      fallbackStorageKey(draft.key),
      JSON.stringify(draft)
    );
    return;
  }

  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.objectStore(STORE_NAME).put(draft);
  });
}

export async function clearDraft(key: string): Promise<void> {
  if (!hasIndexedDb()) {
    window.localStorage.removeItem(fallbackStorageKey(key));
    return;
  }

  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.objectStore(STORE_NAME).delete(key);
  });
}
