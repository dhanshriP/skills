async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export const api = {
  analyze: (b) => post("/api/analyze", b),
  solutions: (b) => post("/api/solutions", b),
  implementPr: (b) => post("/api/implement-pr", b),
  raisePr: (b) => post("/api/raise-pr", b),
};
