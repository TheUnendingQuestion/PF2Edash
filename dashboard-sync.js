// --- CONFIGURATION ---
const SUPABASE_URL = "https://dgsqiohgkkbjlgwfspwm.supabase.co/rest/v1/event_logs?on_conflict=message_id";
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRnc3Fpb2hna2tiamxnd2ZzcHdtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI1MTQwMzUsImV4cCI6MjEwODA5MDAzNX0.iJpDiVaLqi-yY-KW4aHvXz8maJ9UT2F8VsWKuI-ohXA";

async function sendToDashboard(data) {
  try {
    const res = await fetch(SUPABASE_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "apikey": SUPABASE_KEY,
        "Authorization": `Bearer ${SUPABASE_KEY}`,
        "Prefer": "return=minimal,resolution=ignore-duplicates"
      },
      body: JSON.stringify(data)
    });
    if (!res.ok) console.error("Dashboard error response:", await res.text());
  } catch (err) {
    console.error("Dashboard POST failed:", err);
  }
}

function calculateActorWealth(actor) {
  if (!actor) return 0;
  let wealthObj = actor.inventory?.totalWealth ?? actor.system?.details?.wealth;
  if (wealthObj) {
    let gp = wealthObj.goldValue ?? wealthObj.value;
    if (gp !== undefined && !isNaN(gp)) return Number(gp);
  }
  if (actor.items) {
    let totalGP = 0;
    for (const item of actor.items.values()) {
      if (item.type === "treasure") {
        const systemData = item.system;
        const quantity = systemData?.quantity?.value ?? 1;
        const denomination = systemData?.denomination?.value; 
        const valueObj = systemData?.value;
        let itemGpPerUnit = typeof valueObj === "object" && valueObj !== null ? (valueObj[denomination] ?? valueObj.gp ?? 0) : (typeof valueObj === "number" ? valueObj : 0);
        let multiplier = denomination === "cp" ? 0.01 : denomination === "sp" ? 0.1 : denomination === "gp" ? 1 : denomination === "pp" ? 10 : 1;
        totalGP += (itemGpPerUnit * quantity * multiplier);
      }
    }
    return Number(totalGP);
  }
  return 0;
}

let lastDamageRoller = null; // Tracks who rolled the most recent damage card

// --- HOOKS ---

Hooks.on("createChatMessage", (message) => {
  // Only let the client that authored the message send it to Supabase
  if (message.author?.id !== game.user.id) return;

  const content = message.content ? message.content.toLowerCase() : "";
  const activeActor = message.actor;
  const activeActorName = activeActor ? activeActor.name : null;
  const pf2eFlags = message.flags?.pf2e;
  const context = pf2eFlags?.context;

  // Record who rolled damage so AOE applications can attribute damage back to them
  if (message.isRoll && context?.type === "damage-roll" && activeActor?.type === "character") {
    lastDamageRoller = activeActor.name;
  }

 // 1. Detect Damage Taken (1 entry per target hit -> 4 targets x 20 = 80)
  if (content.includes("takes") && content.includes("damage")) {
    const match = message.content.match(/([0-9]+)\s+damage/i);
    const targetName = message.speaker?.alias || activeActorName;

    // Try to resolve the originating actor from PF2e's appliedDamage flag, falling back to lastDamageRoller
    let dealerName = lastDamageRoller;
    const originUuid = pf2eFlags?.appliedDamage?.origin;
    if (originUuid) {
      const originDoc = fromUuidSync(originUuid);
      const originActor = originDoc?.actor ?? originDoc;
      if (originActor?.name) dealerName = originActor.name;
    }

    if (match && targetName) {
      sendToDashboard({
        message_id: message.id,
        character_name: targetName,
        source_actor: dealerName,
        event_type: "damage_taken",
        value: Number(match[1]),
        timestamp: new Date().toISOString()
      });
    }
  }
  if (!activeActor || activeActor.type !== "character") return;

  const pf2eFlags = message.flags?.pf2e;
  const context = pf2eFlags?.context;

  // 2. Detect Healing Done
  if (message.isRoll && context?.type === "damage-roll") {
    const isHealing = message.rolls[0]?.options?.evaluateHealing ||
                      message.flavor?.toLowerCase().includes("heal") ||
                      message.flavor?.toLowerCase().includes("treat wounds") ||
                      pf2eFlags?.damage?.some(d => d.type === "vitality" || d.type === "healing");

    if (isHealing) {
      sendToDashboard({
        message_id: message.id,
        character_name: activeActor.name,
        event_type: "healing_done",
        value: message.rolls[0]?.total,
        timestamp: new Date().toISOString()
      });
      return;
    }
  }

  if ((content.includes("healed for") || content.includes("healed")) && activeActorName) {
    const match = message.content.match(/([0-9]+)\s+damage/i);
    if (match) {
      sendToDashboard({
        message_id: message.id,
        character_name: activeActorName,
        event_type: "healing_done",
        value: Number(match[1]),
        timestamp: new Date().toISOString()
      });
      return;
    }
  }

  // 3. Standard D20 Rolls
  if (message.isRoll && context && context.type !== "damage-roll") {
    const rollTotal = message.rolls[0]?.total;
    const d20Result = message.rolls[0]?.terms[0]?.results[0]?.result;

    let skillName = null;
    if (context.type === "skill-check") {
      skillName = context.domains?.[0] || null;
    }

    sendToDashboard({
      message_id: message.id,
      character_name: activeActor.name,
      event_type: context.type,
      value: rollTotal,
      raw_d20: d20Result,
      outcome: context.outcome || "unknown",
      skill_name: skillName,
      timestamp: new Date().toISOString()
    });
  }

  // 4. Offensive Damage Dealt Rolls
  if (message.isRoll && context?.type === "damage-roll") {
    sendToDashboard({
      message_id: message.id,
      character_name: activeActor.name,
      event_type: "damage_dealt",
      value: message.rolls[0]?.total,
      timestamp: new Date().toISOString()
    });
  }

  // 5. Spells Cast
  const isSpellOrigin = pf2eFlags?.origin?.type === "spell";
  const isDamageRoll = context?.type === "damage-roll";

  if (isSpellOrigin && !isDamageRoll) {
    sendToDashboard({
      message_id: message.id,
      character_name: activeActor.name,
      event_type: "spell_cast",
      spell_name: message.item?.name || "Unknown Spell",
      timestamp: new Date().toISOString()
    });
  }
});

// Wealth Tracking Hooks
Hooks.on("updateItem", (item) => {
  const actor = item.actor;
  if (!actor) return;
  if (actor.type === "character") {
    sendToDashboard({
      character_name: actor.name,
      event_type: "wealth_update",
      value: calculateActorWealth(actor),
      timestamp: new Date().toISOString()
    });
  } else if (actor.type === "party") {
    sendToDashboard({
      character_name: "Party Total",
      event_type: "party_wealth_update",
      value: calculateActorWealth(actor),
      timestamp: new Date().toISOString()
    });
  }
});

Hooks.on("updateActor", (actor) => {
  if (actor.type === "party") {
    sendToDashboard({
      character_name: "Party Total",
      event_type: "party_wealth_update",
      value: calculateActorWealth(actor),
      timestamp: new Date().toISOString()
    });
  }
});
