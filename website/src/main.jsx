import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { request } from "./api";
import "./styles.css";

const stamp = (v) =>
  v
    ? new Date(v.includes("T") ? v : v + "T12:00:00").toLocaleString(
        undefined,
        {
          dateStyle: "medium",
          ...(v.includes("T") ? { timeStyle: "short" } : {}),
        },
      )
    : "Not scheduled";
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const F = (name, label, type = "text", value = "", extra = {}) => ({
  name,
  label,
  type,
  value,
  ...extra,
});
const petFields = (p) => [
  F("name", "Pet name", "text", p.name || "", { maxLength: 120 }),
  F("species", "Species", "text", p.species || "Dog", { maxLength: 100 }),
  F("breed", "Breed", "text", p.breed || "", {
    required: false,
    maxLength: 120,
  }),
  F("age_months", "Age in months", "number", p.age_months ?? 0, {
    min: 0,
    max: 1200,
  }),
  F("gender", "Gender", "text", p.gender || "unknown", {
    options: ["unknown", "male", "female"],
  }),
  F("medical_notes", "Medical notes", "textarea", p.medical_notes || "", {
    required: false,
    maxLength: 5000,
  }),
];
const vetFields = (v) => [
  F(
    "specialization",
    "Specialization",
    "text",
    v.specialization || "General care",
    { maxLength: 200 },
  ),
  F("clinic", "Clinic", "text", v.clinic || "", {
    required: false,
    maxLength: 200,
  }),
  F("available", "Accepting appointments", "text", v.available ?? true, {
    options: [
      ["true", "Yes"],
      ["false", "No"],
    ],
    boolean: true,
  }),
];
function Brand() {
  return (
    <div className="brand">
      <span className="brand-icon">🐾</span>
      <div>
        Paw Protectors<small>CONNECTED PET CARE</small>
      </div>
    </div>
  );
}
function Button({ children, onClick, kind = "", ...props }) {
  return (
    <button className={"btn " + kind} onClick={onClick} {...props}>
      {children}
    </button>
  );
}
function Empty({ children }) {
  return <div className="empty">{children}</div>;
}
function Heading({ title, children, action }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{children}</p>
      </div>
      {action}
    </div>
  );
}
function Field({ field: f }) {
  const id = "field-" + f.name,
    props = {
      id,
      name: f.name,
      defaultValue: String(f.value ?? ""),
      required: f.required !== false,
      min: f.min,
      max: f.max,
      maxLength: f.maxLength,
      minLength: f.minLength,
    };
  return (
    <React.Fragment>
      <label htmlFor={id}>{f.label}</label>
      {f.options ? (
        <select {...props}>
          {f.options.map((o) => {
            const [value, label] = Array.isArray(o) ? o : [o, o];
            return (
              <option key={value} value={String(value)}>
                {label}
              </option>
            );
          })}
        </select>
      ) : f.type === "textarea" ? (
        <textarea {...props} />
      ) : (
        <input
          {...props}
          type={f.type}
          autoComplete={f.type === "password" ? "current-password" : undefined}
        />
      )}
    </React.Fragment>
  );
}
function Modal({ config, onClose, onSaved }) {
  const ref = useRef(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    ref.current.showModal();
  }, []);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = Object.fromEntries(new FormData(e.currentTarget));
      for (const f of config.fields) {
        if (f.type === "number") data[f.name] = Number(data[f.name]);
        if (f.boolean) data[f.name] = data[f.name] === "true";
        if (f.nullable && !data[f.name]) data[f.name] = null;
        if (f.type === "datetime-local")
          data[f.name] = new Date(data[f.name]).toISOString();
      }
      await config.save(data);
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      aria-labelledby="dialog-title"
    >
      <div className="dialog-head">
        <h2 id="dialog-title">{config.title}</h2>
        <button
          className="close"
          disabled={busy}
          onClick={onClose}
          aria-label="Close"
        >
          ×
        </button>
      </div>
      <form onSubmit={submit}>
        {config.fields.map((f) => (
          <Field key={f.name} field={f} />
        ))}
        {error && (
          <div role="alert" className="inline-error">
            {error}
          </div>
        )}
        <div className="form-actions">
          <Button type="button" kind="ghost" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : config.label || "Save changes"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
function Photo({ pet, token }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let url,
      active = true;
    const controller = new AbortController();
    setSrc("");
    if (pet.image_path)
      fetch(`/pets/${pet.id}/image`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      })
        .then((r) => {
          if (!r.ok) throw new Error();
          return r.blob();
        })
        .then((blob) => {
          if (active) {
            url = URL.createObjectURL(blob);
            setSrc(url);
          }
        })
        .catch(() => {});
    return () => {
      active = false;
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [pet.id, pet.image_path, token]);
  return (
    <div
      className={
        "pet-face " + (pet.species.toLowerCase() === "cat" ? "cat" : "")
      }
    >
      {src ? (
        <img src={src} alt={pet.name} />
      ) : (
        <span>{pet.species.toLowerCase() === "cat" ? "🐈" : "🐕"}</span>
      )}
    </div>
  );
}
function Auth({ onLogin }) {
  const [register, setRegister] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(
        await request(
          register ? "/auth/register" : "/auth/login",
          "",
          "POST",
          Object.fromEntries(new FormData(e.currentTarget)),
        ),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth">
      <section className="auth-story">
        <Brand />
        <div>
          <p className="eyebrow">FOR THE ONES WHO MAKE LIFE BETTER</p>
          <h1>
            A little care.
            <br />A happier
            <br />
            companion.
          </h1>
          <p className="story-copy">
            Keep their care connected, from a first vaccination to the next
            happy check-up.
          </p>
          <div className="pet-art">
            <span>🐕</span>
            <span>🐈</span>
          </div>
        </div>
        <p>♡ Health records together · ✚ Trusted veterinary care</p>
      </section>
      <main className="auth-panel">
        <div className="auth-box">
          <h1>{register ? "Start your care story." : "Good to see you."}</h1>
          <p className="muted">Your Android account works here too.</p>
          <div className="auth-tabs">
            <button
              onClick={() => {
                setRegister(false);
                setError("");
              }}
              className={!register ? "active" : ""}
            >
              Log in
            </button>
            <button
              onClick={() => {
                setRegister(true);
                setError("");
              }}
              className={register ? "active" : ""}
            >
              Create account
            </button>
          </div>
          <form onSubmit={submit} key={register ? "register" : "login"}>
            {register && (
              <Field
                field={F("name", "Your name", "text", "", { maxLength: 120 })}
              />
            )}
            <Field field={F("email", "Email address", "email")} />
            <Field
              field={F("password", "Password", "password", "", {
                minLength: register ? 10 : 1,
                maxLength: 128,
              })}
            />
            {error && (
              <div className="inline-error" role="alert">
                {error}
              </div>
            )}
            <div className="actions">
              <Button type="submit" kind="full" disabled={busy}>
                {busy
                  ? "Connecting…"
                  : register
                    ? "Create account →"
                    : "Log in →"}
              </Button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
}

function App() {
  const [token, setToken] = useState(
      () => sessionStorage.getItem("paw_web_token") || "",
    ),
    [user, setUser] = useState(null),
    [restoring, setRestoring] = useState(!!token),
    [route, setRoute] = useState({ page: "dashboard" }),
    [revision, setRevision] = useState(0),
    [data, setData] = useState(null),
    [error, setError] = useState(""),
    [modal, setModal] = useState(null),
    [notice, setNotice] = useState("");
  const go = (page, id) => {
    setData(null);
    setError("");
    setRoute({ page, id });
  };
  const reload = () => setRevision((v) => v + 1);
  function clearSession() {
    sessionStorage.removeItem("paw_web_token");
    setToken("");
    setUser(null);
    setModal(null);
    setData(null);
  }
  const api = async (path, method, data, signal) => {
    try {
      return await request(path, token, method, data, signal);
    } catch (e) {
      if (e.status === 401) clearSession();
      throw e;
    }
  };
  useEffect(() => {
    if (!token) return;
    let active = true;
    const c = new AbortController();
    request("/auth/me", token, "GET", undefined, c.signal)
      .then((u) => {
        if (active) setUser(u);
      })
      .catch((e) => {
        if (active && e.name !== "AbortError") clearSession();
      })
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
      c.abort();
    };
  }, [token]);
  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(""), 6000);
    return () => clearTimeout(id);
  }, [notice]);
  useEffect(() => {
    if (!user) return;
    const c = new AbortController();
    let active = true;
    setData(null);
    setError("");
    const get = (p) => api(p, "GET", undefined, c.signal);
    async function load() {
      const { page, id } = route;
      let result;
      if (page === "dashboard") {
        const [pets, visits, reminders, vets] = await Promise.all(
          ["/pets", "/appointments", "/reminders", "/veterinarians"].map(get),
        );
        result = { pets, visits, reminders, vets };
      } else if (page === "pet") {
        const [pet, vaccinations, medical] = await Promise.all(
          [
            `/pets/${id}`,
            `/pets/${id}/vaccinations`,
            `/pets/${id}/medical-records`,
          ].map(get),
        );
        result = { pet, vaccinations, medical };
      } else if (page === "slots") {
        const [slots, vets] = await Promise.all([
          get(`/slots?veterinarian_id=${id}`),
          get("/veterinarians"),
        ]);
        result = { slots, vet: vets.find((v) => v.id === Number(id)) };
      } else
        result = await get(
          {
            pets: "/pets",
            vets: "/veterinarians",
            appointments: "/appointments",
            reminders: "/reminders",
            admin: "/admin/analytics",
            users: "/admin/users",
            audit: "/admin/audit",
          }[page],
        );
      if (active) setData(result);
    }
    load().catch((e) => {
      if (active && e.name !== "AbortError") setError(e.message);
    });
    return () => {
      active = false;
      c.abort();
    };
  }, [user, token, route, revision]);
  function login(response) {
    sessionStorage.setItem("paw_web_token", response.token);
    setToken(response.token);
    setUser(response.user);
    setRoute({ page: "dashboard" });
  }
  function form(title, fields, path, method = "POST", extra = {}, after) {
    setModal({
      title,
      fields,
      save: async (d) => {
        await api(path, method, { ...d, ...extra });
        if (after) go(...after);
        else reload();
      },
    });
  }
  async function perform(fn) {
    try {
      await fn();
    } catch (e) {
      setNotice(e.message);
    }
  }
  async function mutate(path, message, method = "POST") {
    if (!window.confirm(message)) return;
    await api(path, method);
    setNotice("Updated successfully");
    reload();
  }
  const manageVet = (v) =>
    user.role === "admin" || (user.role === "vet" && v.user_id === user.id);
  async function addVet() {
    const [users, vets] = await Promise.all([
      api("/admin/users"),
      api("/veterinarians"),
    ]);
    const eligible = users.filter(
      (u) =>
        u.role === "vet" && u.active && !vets.some((v) => v.user_id === u.id),
    );
    if (!eligible.length)
      throw new Error("Assign an active account the veterinarian role first.");
    form(
      "Add veterinarian",
      [
        F("user_id", "Veterinarian account", "number", eligible[0].id, {
          options: eligible.map((u) => [u.id, u.name]),
        }),
        ...vetFields({}),
      ],
      "/veterinarians",
    );
  }
  async function book(slot) {
    const pets = (await api("/pets")).filter((p) => p.owner_id === user.id);
    if (!pets.length) throw new Error("Add your own pet before booking.");
    form(
      "Book a visit",
      [
        F("pet_id", "Choose your pet", "number", pets[0].id, {
          options: pets.map((p) => [p.id, p.name]),
        }),
        F("reason", "Reason for visit", "textarea", "", {
          required: false,
          maxLength: 1000,
        }),
      ],
      "/appointments",
      "POST",
      { slot_id: slot.id },
      ["appointments"],
    );
  }
  async function upload(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024)
      throw new Error("Choose a photo under 5 MB.");
    const body = new FormData();
    body.append("file", file);
    await api(`/pets/${route.id}/image`, "POST", body);
    reload();
  }
  function card(p) {
    return (
      <article className="card" key={p.id}>
        <Photo pet={p} token={token} />
        <h3>{p.name}</h3>
        <p>{p.breed || p.species}</p>
        <div className="pet-meta">
          {p.age_months} months · {p.gender}
          <span className="pill">{p.species}</span>
        </div>
        <div className="actions">
          <Button kind="secondary" onClick={() => go("pet", p.id)}>
            View health profile
          </Button>
        </div>
      </article>
    );
  }
  function visit(a) {
    return (
      <article className="row-card" key={a.id}>
        <div>
          <h3>
            {a.pet_name} <span className={"pill " + a.status}>{a.status}</span>
          </h3>
          <p>
            {a.veterinarian_name} · {stamp(a.starts_at)}
          </p>
          <p>{a.reason}</p>
        </div>
        {a.status === "booked" && (
          <div className="actions">
            <Button
              kind="ghost"
              onClick={() =>
                perform(() =>
                  mutate(
                    `/appointments/${a.id}/cancel`,
                    "Cancel this booked visit?",
                  ),
                )
              }
            >
              Cancel
            </Button>
            {user.role !== "owner" && (
              <Button
                onClick={() =>
                  perform(() =>
                    mutate(
                      `/appointments/${a.id}/complete`,
                      "Mark this visit completed?",
                    ),
                  )
                }
              >
                Complete
              </Button>
            )}
          </div>
        )}
      </article>
    );
  }
  function content() {
    const { page, id } = route;
    if (page === "dashboard") {
      const upcoming = data.visits.filter((a) => a.status === "booked");
      return (
        <>
          <Heading title="A good day for a little care.">
            Welcome back, {user.name.split(" ")[0]}.
          </Heading>
          <section className="hero">
            <div>
              <p className="eyebrow">HAPPY PETS, PEACE OF MIND</p>
              <h1>
                Every little moment
                <br />
                of care matters.
              </h1>
              <p>
                Keep their health history close and their next check-up a little
                easier.
              </p>
              <Button
                kind="light"
                onClick={() =>
                  go(user.role === "vet" ? "appointments" : "vets")
                }
              >
                {user.role === "vet"
                  ? "Manage appointments"
                  : "Find a veterinarian"}
              </Button>
            </div>
            <div className="hero-paw">🐾</div>
          </section>
          <div className="stats">
            {[
              ["Pet profiles", data.pets.length],
              ["Booked visits", upcoming.length],
              ["Care reminders", data.reminders.length],
              ["Available vets", data.vets.filter((v) => v.available).length],
            ].map(([label, n]) => (
              <div className="stat" key={label}>
                <small>{label}</small>
                <strong>{n}</strong>
              </div>
            ))}
          </div>
          <div className="section-title">
            <h2>Your companions</h2>
            <Button kind="ghost" onClick={() => go("pets")}>
              View all →
            </Button>
          </div>
          <div className="grid">
            {data.pets.slice(0, 3).map(card)}
            {!data.pets.length && (
              <Empty>Add a pet to start their care story.</Empty>
            )}
          </div>
          <h2 className="section-title">Upcoming visits</h2>
          {upcoming.slice(0, 3).map(visit)}
          {!upcoming.length && <Empty>No booked visits.</Empty>}
        </>
      );
    }
    if (page === "pets")
      return (
        <>
          <Heading
            title={
              user.role === "vet" ? "Pets in your care" : "Your companions"
            }
            action={
              user.role !== "vet" && (
                <Button onClick={() => form("Add pet", petFields({}), "/pets")}>
                  + Add pet
                </Button>
              )
            }
          >
            Profiles, vaccinations and health notes.
          </Heading>
          <div className="grid">
            {data.map(card)}
            {!data.length && <Empty>No pet profiles yet.</Empty>}
          </div>
        </>
      );
    if (page === "pet") {
      const p = data.pet;
      return (
        <>
          <Button kind="ghost" onClick={() => go("pets")}>
            ← Back to pets
          </Button>
          <Heading title={p.name + "’s health profile"}>
            A complete picture of their care.
          </Heading>
          <div className="two-col">
            <article className="card">
              <Photo pet={p} token={token} />
              <h2>{p.name}</h2>
              <p>
                {p.species} · {p.breed}
              </p>
              <p>
                {p.age_months} months · {p.gender}
              </p>
              <p className="note">
                {p.medical_notes || "No additional medical notes."}
              </p>
              {user.role !== "vet" && (
                <>
                  <div className="actions">
                    <Button
                      kind="secondary"
                      onClick={() =>
                        form(
                          "Edit pet profile",
                          petFields(p),
                          `/pets/${id}`,
                          "PUT",
                        )
                      }
                    >
                      Edit profile
                    </Button>
                    <Button
                      kind="danger"
                      onClick={() =>
                        perform(async () => {
                          if (
                            !confirm(
                              "Delete this pet? Pets with care records must be retained.",
                            )
                          )
                            return;
                          await api(`/pets/${id}`, "DELETE");
                          go("pets");
                        })
                      }
                    >
                      Delete
                    </Button>
                  </div>
                  <label htmlFor="photo">
                    Change photo (JPEG/PNG, max 5 MB)
                  </label>
                  <input
                    id="photo"
                    type="file"
                    accept="image/jpeg,image/png"
                    onChange={(e) => perform(() => upload(e))}
                  />
                </>
              )}
            </article>
            <div>
              <h2>Vaccination records</h2>
              <Button
                kind="secondary"
                onClick={() =>
                  form(
                    "Add vaccination",
                    [
                      F("vaccine", "Vaccine", "text", "Rabies", {
                        maxLength: 200,
                      }),
                      F("administered_on", "Administered on", "date", today()),
                      F("next_due", "Next due", "date", "", {
                        required: false,
                        nullable: true,
                      }),
                    ],
                    `/pets/${id}/vaccinations`,
                  )
                }
              >
                + Add vaccination
              </Button>
              {data.vaccinations.map((v) => (
                <article className="card record" key={v.id}>
                  <h3>{v.vaccine}</h3>
                  <p>Given {stamp(v.administered_on)}</p>
                  <p>Next due: {stamp(v.next_due)}</p>
                </article>
              ))}
              {!data.vaccinations.length && (
                <Empty>No vaccinations recorded.</Empty>
              )}
              <h2 className="section-title">Medical history</h2>
              {user.role === "vet" && (
                <Button
                  onClick={() =>
                    form(
                      "Add clinical record",
                      [
                        F("diagnosis", "Diagnosis", "textarea", "", {
                          maxLength: 5000,
                        }),
                        F("treatment", "Treatment", "textarea", "", {
                          required: false,
                          maxLength: 5000,
                        }),
                      ],
                      `/pets/${id}/medical-records`,
                    )
                  }
                >
                  + Clinical record
                </Button>
              )}
              {data.medical.map((m) => (
                <article className="card record" key={m.id}>
                  <h3>{m.diagnosis}</h3>
                  <p className="note">{m.treatment}</p>
                  <p>
                    {m.veterinarian_name} · {stamp(m.recorded_at)}
                  </p>
                </article>
              ))}
              {!data.medical.length && <Empty>No clinical records yet.</Empty>}
            </div>
          </div>
        </>
      );
    }
    if (page === "vets")
      return (
        <>
          <Heading
            title="A trusted team for their care."
            action={
              user.role === "admin" && (
                <Button onClick={() => perform(addVet)}>
                  + Add veterinarian
                </Button>
              )
            }
          >
            Find a clinic and choose a visit.
          </Heading>
          <div className="grid">
            {data.map((v) => (
              <article className="card" key={v.id}>
                <div className="vet-avatar">✚</div>
                <h3>{v.name}</h3>
                <p>{v.specialization}</p>
                <p>{v.clinic}</p>
                <span className="pill">
                  {v.available ? "Available" : "Unavailable"}
                </span>
                <div className="actions">
                  <Button kind="secondary" onClick={() => go("slots", v.id)}>
                    View schedule
                  </Button>
                  {manageVet(v) && (
                    <Button
                      kind="ghost"
                      onClick={() =>
                        form(
                          "Veterinarian profile",
                          vetFields(v),
                          `/veterinarians/${v.id}`,
                          "PUT",
                          { user_id: v.user_id },
                        )
                      }
                    >
                      Edit profile
                    </Button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </>
      );
    if (page === "slots") {
      const v = data.vet;
      if (!v) return <Empty>Veterinarian not found.</Empty>;
      return (
        <>
          <Button kind="ghost" onClick={() => go("vets")}>
            ← Back to veterinarians
          </Button>
          <Heading
            title={v.name + " · Schedule"}
            action={
              manageVet(v) && (
                <Button
                  onClick={() =>
                    form(
                      "Create appointment slot",
                      [
                        F(
                          "starts_at",
                          "Starts at (local time)",
                          "datetime-local",
                        ),
                        F("ends_at", "Ends at (local time)", "datetime-local"),
                      ],
                      "/slots",
                      "POST",
                      { veterinarian_id: v.id },
                    )
                  }
                >
                  + Create slot
                </Button>
              )
            }
          >
            Available future appointment slots.
          </Heading>
          {data.slots.map((s) => (
            <article className="row-card" key={s.id}>
              <div>
                <h3>{stamp(s.starts_at)}</h3>
                <p>
                  Until {stamp(s.ends_at)} · {v.clinic}
                </p>
              </div>
              <div className="actions">
                {user.role !== "vet" && (
                  <Button onClick={() => perform(() => book(s))}>
                    Book visit
                  </Button>
                )}
                {manageVet(v) && (
                  <Button
                    kind="ghost"
                    onClick={() =>
                      perform(() =>
                        mutate(
                          `/slots/${s.id}`,
                          "Remove this available slot?",
                          "DELETE",
                        ),
                      )
                    }
                  >
                    Remove
                  </Button>
                )}
              </div>
            </article>
          ))}
          {!data.slots.length && <Empty>No open slots.</Empty>}
        </>
      );
    }
    if (page === "appointments")
      return (
        <>
          <Heading
            title="Visits, past and upcoming."
            action={
              user.role !== "vet" && (
                <Button onClick={() => go("vets")}>+ Book a visit</Button>
              )
            }
          >
            Every appointment close at hand.
          </Heading>
          {data.map(visit)}
          {!data.length && <Empty>No appointments yet.</Empty>}
        </>
      );
    if (page === "reminders")
      return (
        <>
          <Heading title="A gentle nudge for their health.">
            Upcoming care reminders.
          </Heading>
          {data.map((r) => (
            <article className="row-card" key={r.id}>
              <div>
                <h3>{r.message}</h3>
                <p>Due {stamp(r.due_at)}</p>
              </div>
              <Button
                kind="secondary"
                onClick={() =>
                  perform(async () => {
                    await api(`/reminders/${r.id}/acknowledge`, "POST");
                    reload();
                  })
                }
              >
                Acknowledge
              </Button>
            </article>
          ))}
          {!data.length && <Empty>You’re all caught up.</Empty>}
        </>
      );
    if (page === "admin")
      return (
        <>
          <Heading title="Your administration desk.">
            Manage access and monitor bookings.
          </Heading>
          <div className="grid">
            {[
              ["Users", data.users],
              ["Pets", data.pets],
              ["Veterinarians", data.veterinarians],
              ["Booked visits", data.booked],
              ["Cancelled visits", data.cancelled],
              ["Audit events", data.audit_events],
            ].map(([label, n]) => (
              <article className="stat" key={label}>
                <small>{label}</small>
                <strong>{n}</strong>
              </article>
            ))}
          </div>
          <div className="actions">
            {[
              ["User accounts", "users"],
              ["Veterinarians", "vets"],
              ["Monitor visits", "appointments"],
              ["Transaction audit", "audit"],
            ].map(([label, page]) => (
              <Button key={page} onClick={() => go(page)}>
                {label}
              </Button>
            ))}
          </div>
        </>
      );
    if (page === "users")
      return (
        <>
          <Heading title="User accounts">Roles and account access.</Heading>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Access</th>
                </tr>
              </thead>
              <tbody>
                {data.map((u) => (
                  <tr key={u.id}>
                    <td>{u.name}</td>
                    <td>{u.email}</td>
                    <td>{u.role}</td>
                    <td>{u.active ? "Active" : "Disabled"}</td>
                    <td>
                      <Button
                        kind="secondary"
                        onClick={() =>
                          form(
                            "Manage " + u.name,
                            [
                              F("role", "Role", "text", u.role, {
                                options: ["owner", "vet", "admin"],
                              }),
                              F("active", "Account access", "text", u.active, {
                                options: [
                                  ["true", "Active"],
                                  ["false", "Disabled"],
                                ],
                                boolean: true,
                              }),
                            ],
                            `/admin/users/${u.id}`,
                            "PUT",
                          )
                        }
                      >
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      );
    if (page === "audit")
      return (
        <>
          <Heading title="Transaction audit">
            Latest 200 committed database changes.
          </Heading>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Action</th>
                  <th>Record</th>
                  <th>Actor / Transaction</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id}>
                    <td>{stamp(a.created_at)}</td>
                    <td>{a.action}</td>
                    <td>
                      {a.entity} #{a.entity_id}
                    </td>
                    <td>
                      {a.actor_id ?? "System"} / {a.transaction_id}
                    </td>
                    <td className="audit-details">
                      {JSON.stringify(a.details, null, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      );
  }
  if (restoring) return <div className="boot">Restoring session…</div>;
  if (!user)
    return (
      <>
        <Auth onLogin={login} />
        {notice && (
          <div id="toast" role="status">
            {notice}
          </div>
        )}
      </>
    );
  const nav = [
    ["dashboard", "◫", "Overview"],
    ["pets", "♡", "My pets"],
    ["vets", "✚", "Veterinarians"],
    ["appointments", "▦", "Appointments"],
    ["reminders", "◷", "Reminders"],
    ...(user.role === "admin" ? [["admin", "⚙", "Administration"]] : []),
  ];
  return (
    <>
      <div className="shell">
        <aside className="sidebar">
          <Brand />
          <p className="nav-label">YOUR CARE SPACE</p>
          <nav className="nav" aria-label="Main navigation">
            {nav.map(([page, icon, label]) => (
              <button
                key={page}
                className={route.page === page ? "active" : ""}
                onClick={() => go(page)}
              >
                <span className="nav-icon">{icon}</span>
                {label}
              </button>
            ))}
          </nav>
          <div className="sidebar-note">
            <strong>Care, always connected.</strong>Your phone and browser share
            the same records.
          </div>
          <button
            className="logout"
            onClick={() =>
              perform(async () => {
                await api("/auth/logout", "POST");
                clearSession();
              })
            }
          >
            ↪ Log out
          </button>
        </aside>
        <main className="main">
          <header className="topbar">
            <div className="breadcrumb">
              Your care space /{" "}
              {nav.find((n) => n[0] === route.page)?.[2] ||
                {
                  pet: "Health profile",
                  slots: "Schedule",
                  users: "User accounts",
                  audit: "Transaction audit",
                }[route.page]}
            </div>
            <div className="user">
              <div>
                <strong>{user.name}</strong>
                <small>
                  {user.role === "owner"
                    ? "Pet owner"
                    : user.role === "vet"
                      ? "Veterinarian"
                      : "Administrator"}
                </small>
              </div>
              <span className="avatar">{user.name.slice(0, 1)}</span>
            </div>
          </header>
          {error ? (
            <>
              <div className="inline-error" role="alert">
                {error}
              </div>
              <Button onClick={reload}>Try again</Button>
            </>
          ) : !data ? (
            <div className="loading">
              <span className="spinner" />
              Loading your records…
            </div>
          ) : (
            content()
          )}
        </main>
      </div>
      {modal && (
        <Modal
          config={modal}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            setNotice("Saved successfully");
          }}
        />
      )}
      {notice && (
        <div id="toast" role="status">
          {notice}
        </div>
      )}
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
