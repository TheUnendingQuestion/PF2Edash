import streamlit as st
from supabase import create_client, Client
import pandas as pd
import altair as alt
from streamlit_autorefresh import st_autorefresh

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="PF2e Campaign Dashboard",
    page_icon="🎲",
    layout="wide"
)

# --- AUTO-REFRESH TIMER ---
# Automatically refreshes the dashboard data every 5 seconds (5000 milliseconds)
count = st_autorefresh(interval=5000, limit=None, key="datarefresh")

# Safely extract secrets with fallback options
#try:
 #   SUPABASE_URL = st.secrets["SUPABASE_URL"]
  #  SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
#except Exception:
    # Fallback if nested under a [connections.supabase] section block
 #   SUPABASE_URL = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
  #  SUPABASE_KEY = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]

# Verification check in logs: prints length and prefix, never the full key
#print(f"DEBUG URL Loaded: {SUPABASE_URL[:15]}...")
#print(f"DEBUG Key Length: {len(SUPABASE_KEY)}")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# --- SUPABASE CONNECTION ---
# Fetch credentials securely from Streamlit Secrets
SUPABASE_URL = st.secrets["SUPABASE_URL"].strip()
SUPABASE_KEY = st.secrets["SUPABASE_KEY"].strip()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- FETCH DATA ---
@st.cache_data(ttl=5) # Refreshes cache every 5 seconds for live feel
def load_data():
    #response = supabase.table("event_logs").select("*").order("id", desc=True).execute()
    response = supabase.table("event_logs").select("*").execute() # debug - removed order by to determine if there is a clash with bkup table
    if response.data:
        return pd.DataFrame(response.data)
    return pd.DataFrame(response.data)

df = load_data()

# --- TITLE ---
st.title("🛡️ Pathfinder 2e: Live Campaign Dashboard")
st.markdown("Tracking dice rolls, wealth, spells, and damage live from Foundry VTT.")

if df.empty:
    st.info("Waiting for data... Play a session in Foundry and trigger some rolls or wealth changes!")
else:
    # --- SIDEBAR FILTERS ---
    st.sidebar.header("Filters")
    characters = df["character_name"].dropna().unique().tolist()
    selected_char = st.sidebar.selectbox("Filter by Character", ["All"] + characters)
    
    if selected_char != "All":
        df = df[df["character_name"] == selected_char]

    # --- TOP METRICS ROW ---
    col1, col2, col3, col4 = st.columns(4)
    
    total_rolls = len(df[df["event_type"].isin(["attack-roll", "saving-throw", "skill-check"])])
    nat_20s = len(df[df["raw_d20"] == 20])
    nat_1s = len(df[df["raw_d20"] == 1])
    total_damage = df[df["event_type"] == "damage_dealt"]["value"].sum()

    col1.metric("Total Rolls Logged", total_rolls)
    col2.metric("Natural 20s 🎯", nat_20s, delta=f"{nat_20s} crits")
    col3.metric("Natural 1s 💀", nat_1s, delta_color="inverse")
    col4.metric("Total Damage Dealt", f"{int(total_damage):,} dmg")

    st.markdown("---")

    # --- TABS FOR DIFFERENT STATS ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🎲 Dice & Combat",
        "🎯 Skill Success Rates",
        "🔮 Spells Cast",
        "💰 Party Wealth",
        "📜 Raw Event Log",
    ])

    with tab1:
        st.subheader("🎲 Natural 20 vs Natural 1 Tracker")
        roll_counts = df[df["raw_d20"].isin([1, 20])].groupby(["character_name", "raw_d20"]).size().reset_index(name="count")
        
        if not roll_counts.empty:
            chart = alt.Chart(roll_counts).mark_bar().encode(
                x=alt.X("character_name:N", title="Character"),
                y=alt.Y("count:Q", title="Count"),
                color=alt.Color("raw_d20:N", title="d20 Result (1 or 20)", scale=alt.Scale(domain=[1, 20], range=["#e74c3c", "#2ecc71"]))
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No Natural 1s or 20s logged yet.")

        st.markdown("---")
        st.subheader("⚔️ Attack Roll Success Rates")

        # Filter specifically for attack rolls
        attacks_df = df[df["event_type"] == "attack-roll"]

        if not attacks_df.empty:
            # Map outcomes to success vs failure for attacks
            def categorize_attack_outcome(outcome):
                if outcome in ["success", "criticalSuccess"]:
                    return "Successful"
                elif outcome in ["failure", "criticalFailure"]:
                    return "Unsuccessful"
                return "Other"

            attacks_df["attack_category"] = attacks_df["outcome"].apply(categorize_attack_outcome)

            # Aggregate stats per character
            attack_table_data = []
            for character, group in attacks_df.groupby("character_name"):
                total_attacks = len(group)
                successful_attacks = len(group[group["attack_category"] == "Successful"])
                unsuccessful_attacks = len(group[group["attack_category"] == "Unsuccessful"])
                success_rate = (successful_attacks / total_attacks) if total_attacks > 0 else 0.0

                attack_table_data.append({
                    "Character": character,
                    "Total Attacks": total_attacks,
                    "Successful": successful_attacks,
                    "Failed": unsuccessful_attacks,
                    "Success Rate": success_rate
                })

            attack_summary_df = pd.DataFrame(attack_table_data).sort_values(by="Total Attacks", ascending=False)

            # Display the table with progress bars
            st.dataframe(
                attack_summary_df,
                column_config={
                    "Character": st.column_config.TextColumn("Character Name"),
                    "Total Attacks": st.column_config.NumberColumn("Total Attacks"),
                    "Successful": st.column_config.NumberColumn("Hits / Crits 🟢"),
                    "Failed": st.column_config.NumberColumn("Misses / Fails 🔴"),
                    "Success Rate": st.column_config.ProgressColumn(
                        "Success Rate",
                        help="Percentage of attacks resulting in a Hit or Critical Hit",
                        format="%.1f%%",
                        min_value=0.0,
                        max_value=1.0,
                    ),
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No attack rolls logged yet. Roll some strikes in Foundry!")

        # --- DAMAGE TAKEN TABLE ---
        st.markdown("---")
        st.subheader("🩸 Damage Taken Summary")
        damage_taken_df = df[df["event_type"] == "damage_taken"]

        if not damage_taken_df.empty:
            taken_summary = damage_taken_df.groupby("character_name")["value"].agg(
                Total_Damage_Taken="sum", 
                Instances="count"
            ).reset_index().sort_values(by="Total_Damage_Taken", ascending=False)

            st.dataframe(
                taken_summary,
                column_config={
                    "character_name": st.column_config.TextColumn("Character"),
                    "Total_Damage_Taken": st.column_config.NumberColumn("Total HP Lost 🩸"),
                    "Instances": st.column_config.NumberColumn("Times Hurt"),
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No damage taken events logged yet.")

        # --- HEALING DONE TABLE ---
        st.markdown("---")
        st.subheader("🌿 Healing Done Summary")
        healing_df = df[df["event_type"] == "healing_done"]

        if not healing_df.empty:
            healing_summary = healing_df.groupby("character_name")["value"].agg(
                Total_Healing="sum", 
                Heal_Events="count"
            ).reset_index().sort_values(by="Total_Healing", ascending=False)

            st.dataframe(
                healing_summary,
                column_config={
                    "character_name": st.column_config.TextColumn("Character / Healer"),
                    "Total_Healing": st.column_config.NumberColumn("Total HP Restored ✨"),
                    "Heal_Events": st.column_config.NumberColumn("Healing Actions"),
                },
                hide_index=True,
                use_container_width=True
           )
        else:
            st.info("No healing events logged yet.")

    with tab2:
        st.subheader("🎯 Skill Check Performance")
        skills_df = df[df["event_type"] == "skill-check"].dropna(subset=["skill_name"])
        
        if not skills_df.empty:
            # --- 1. PREPARE OUTCOME CATEGORIES ---
            def categorize_outcome(outcome):
                if outcome in ["success", "criticalSuccess"]:
                    return "Successful"
                elif outcome in ["failure", "criticalFailure"]:
                    return "Unsuccessful"
                return "Other"

            skills_df["result_category"] = skills_df["outcome"].apply(categorize_outcome)

            # --- 2. OVERALL CHART ---
            skill_summary_chart = skills_df.groupby(["skill_name", "result_category"]).size().reset_index(name="count")
            
            chart = alt.Chart(skill_summary_chart).mark_bar().encode(
                x=alt.X("skill_name:N", title="Skill"),
                y=alt.Y("count:Q", title="Number of Rolls"),
                color=alt.Color("result_category:N", title="Outcome", scale=alt.Scale(domain=["Successful", "Unsuccessful"], range=["#2ecc71", "#e74c3c"]))
            ).properties(height=300)
            
            st.altair_chart(chart, use_container_width=True)

            st.markdown("---")
            st.subheader("📊 Detailed Skill Stats Table")

            # --- 3. AGGREGATE STATS FOR THE TABLE ---
            # Group by skill name and calculate totals, successes, and failures
            table_data = []
            for skill, group in skills_df.groupby("skill_name"):
                total_rolls = len(group)
                successes = len(group[group["result_category"] == "Successful"])
                failures = len(group[group["result_category"] == "Unsuccessful"])
                success_rate = (successes / total_rolls) if total_rolls > 0 else 0.0
                
                table_data.append({
                    "Skill": skill.capitalize(),
                    "Total Rolls": total_rolls,
                    "Successes": successes,
                    "Failures": failures,
                    "Success Rate": success_rate
                })

            summary_df = pd.DataFrame(table_data)

            # Sort by highest success rate or total rolls by default
            summary_df = summary_df.sort_values(by="Total Rolls", ascending=False)

            # --- 4. DISPLAY FORMATTED TABLE ---
            st.dataframe(
                summary_df,
                column_config={
                    "Skill": st.column_config.TextColumn("Skill Name"),
                    "Total Rolls": st.column_config.NumberColumn("Total Checks"),
                    "Successes": st.column_config.NumberColumn("Successes 🟢"),
                    "Failures": st.column_config.NumberColumn("Failures 🔴"),
                    "Success Rate": st.column_config.ProgressColumn(
                        "Success Rate",
                        help="Percentage of rolls resulting in Success or Critical Success",
                        format="%.1f%%",
                        min_value=0.0,
                        max_value=1.0,
                    ),
                },
                hide_index=True,
                use_container_width=True
            )

        else:
            st.info("No skill checks logged yet. Roll some skills in Foundry!")

    with tab3:
        st.subheader("🔮 Spellcasting Metrics")
        
        # Filter dataframe for spell cast events
        spells_df = df[df["event_type"] == "spell_cast"].dropna(subset=["spell_name"])
        
        if not spells_df.empty:
            # --- 1. OVERALL TOP SPELLS (BAR CHART) ---
            st.markdown("### Most Cast Spells (Party Total)")
            
            top_spells = spells_df.groupby("spell_name").size().reset_index(name="cast_count")
            top_spells = top_spells.sort_values(by="cast_count", ascending=False)
            
            chart = alt.Chart(top_spells).mark_bar().encode(
                x=alt.X("spell_name:N", title="Spell Name", sort="-y"),
                y=alt.Y("cast_count:Q", title="Times Cast"),
                color=alt.Color("spell_name:N", legend=None)
            ).properties(height=300)
            
            st.altair_chart(chart, use_container_width=True)
            
            st.markdown("---")
            
            # --- 2. DETAILED SPELL SUMMARY TABLE ---
            st.markdown("### 📊 Detailed Breakdown per Spell")
            
            spell_table_data = []
            for spell, group in spells_df.groupby("spell_name"):
                total_casts = len(group)
                # Count breakdown per character who cast it
                caster_counts = group["character_name"].value_counts().to_dict()
                casters_str = ", ".join([f"{char} ({count})" for char, count in caster_counts.items()])
                
                spell_table_data.append({
                    "Spell Name": spell,
                    "Total Casts": total_casts,
                    "Casters": casters_str
                })
            
            spell_summary_df = pd.DataFrame(spell_table_data).sort_values(by="Total Casts", ascending=False)
            
            st.dataframe(
                spell_summary_df,
                column_config={
                    "Spell Name": st.column_config.TextColumn("Spell Name"),
                    "Total Casts": st.column_config.NumberColumn("Total Casts ✨"),
                    "Casters": st.column_config.TextColumn("Casters (Count)"),
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No spells logged yet. Cast some spells in Foundry!")
    
    with tab4:
        st.subheader("Wealth Progression (GP)")
        wealth_df = df[df["event_type"].isin(["wealth_update", "party_wealth_update"])]
        if not wealth_df.empty:
            st.line_chart(wealth_df, x="timestamp", y="value", color="character_name")
        else:
            st.write("No wealth updates logged yet.")

    with tab5:
        st.subheader("Recent Game Activity Feed")
        st.dataframe(df[["timestamp", "character_name", "event_type", "skill_name", "value", "spell_name", "outcome"]], use_container_width=True)
    # Auto-refresh mechanism for Streamlit
    if st.button("🔄 Refresh Data"):
        st.rerun()
