from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List
from app.utils.retry import exponential_backoff_retry
from app.utils.format_cases import format_historical_cases_for_prompt
import logging
import json

logger = logging.getLogger(__name__)

class DosAndDonts(BaseModel):
    """Case-specific dos and donts for law enforcement officers"""
    dos: List[str] = Field(
        description="Case-specific dos that reference specific details from the FIR (names, dates, locations, quantities, exhibit numbers, etc.). Each do must be actionable and tied to this particular case's facts, evidence, accused, witnesses, dates, and legal requirements.",
        max_length=15
    )
    donts: List[str] = Field(
        description="Case-specific donts that reference specific details from the FIR (names, dates, locations, quantities, exhibit numbers, etc.). Each don't must be actionable and tied to this particular case's facts, evidence, accused, witnesses, dates, and legal requirements.",
        max_length=15
    )

def format_sections(sections: List[dict] | None) -> str:
    """Format list of section dictionaries into readable text"""
    if not sections:
        return "None"
    
    formatted = []
    for section in sections:
        # Assuming sections have 'section' and 'description' or similar keys
        # Adjust based on your actual structure
        section_text = f"- {section.get('section', 'Unknown')}: {section.get('description', section.get('text', ''))}"
        formatted.append(section_text)
    
    return "\n".join(formatted)

def generate_dos_and_donts(state: WorkflowState) -> dict:
    """
    Generate comprehensive dos and donts from FIR content and forensic guidelines.
    """
    logger.info("Starting dos and donts generation")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for dos and donts generation")
    
    pdf_content = state["pdf_content_in_english"]
    
    # Get historical cases if available
    historical_cases = state.get("historical_cases", [])
    historical_cases_text = format_historical_cases_for_prompt(historical_cases)
    
    # Construct content for LLM
    content_for_llm = f"""You are an expert legal advisor for NDPS cases. Based on the FIR content and legal sections below, generate SPECIFIC, CASE-SPECIFIC dos and donts for law enforcement officers handling THIS PARTICULAR CASE.

CRITICAL REQUIREMENTS:
1. Each do/don't MUST reference specific details from the FIR (names, dates, locations, quantities, exhibit numbers, times, etc.)
2. Make them actionable and tied to THIS specific case, not generic advice
3. Reference specific legal sections where applicable
4. Include procedural requirements specific to the facts of this case
5. Mention specific evidence items, witnesses, and procedures from the FIR
6. USE THE PROVIDED HISTORICAL CASES: Reference the actual historical cases provided below to illustrate similar procedural requirements, common pitfalls, or successful prosecution strategies. Cite specific case titles and key legal principles from these cases when relevant to strengthen the dos/donts.

========================
OFFICIAL NDPS PROCEDURAL GUIDELINES
========================

PRE-RAID PROCEDURES:

1. Recording of Information:
Whenever any information is received regarding availability of a narcotic drug at a particular place or with a particular person, this information should be taken down in writing and forwarded to the SHO/ACP Sub-Division for obtaining necessary orders.

2. Verification of Information:
A preliminary verification of the information through sources and by surveillance, whenever situation demands, should be done.

3. Planning of Operation:
The operation should be well planned so that it can be conducted efficiently in the least possible time. Choosing the right time to strike is crucial specially when both the buyer and seller of the drug are together and are conducting the transaction. Deployment of responsibilities on various participating officers should be done after briefing on the objectives of the operation. Officers deployed for the search should carry their official identity cards.

4. Carrying important papers/articles/Drugs Identification Kit:
The IO should carry the following important articles/paper while making departure for conducting raid:
i. Search proforma
ii. Form of notice under Sec. 67 of the NDPS Act
iii. Arrest memo
iv. Envelopes
v. Seal
vi. Sealing materials
vii. Writing paper
viii. Candles, matchsticks
ix. Digital weighing machine
x. Drug Identification/Test Kit
xi. Other items which may be necessary during the raid

5. Lodging of proper departure Entry:
The IO should made proper and detailed departure DD entry mentioning the details of raiding team members, vehicle through which the raiding team is proceeding to the spot, details of all equipment's being taken to the spot etc.

RAID AND SEIZURE PROCEDURES:

6. Search of Premises:
Before the commencement of the search, the officer should obtain an authorization for the search as per Sec. 41(2) of the NDPS Act. On searching the spot, the officers must immediately gear up for the strike. The entry and exit points must be manned properly and watch should be maintained on the windows and other opening so that nothing can be thrown from exit/verandah, etc.

7. Search Authorization:
If a place is to be searched based on personal knowledge or information taken down in writing, a copy of the grounds of belief or information is to be sent forthwith to his immediate official superior.

8. Procedure for search in premises:
As entry into the premises is sought, the officers should disclose their identity and purpose and offer themselves to be searched. It is to be remembered that the purpose of search may be defeated if anybody is allowed to go out of the premises or make outside calls during the search.

9. Personal Search:
If a person is to be subjected to a personal search, clear offer of search must be given to the accused. He must be informed of his legal right to get his search conducted before Gazetted officer or Magistrate and if such accused so requires then he shall be taken to the nearest Gazetted officer of any of the departments mentioned in section 42 or Magistrate without unnecessary delay. When accused to be searched is a lady then the search is to conducted as per the provisions of section 50(4) of NDPS Act. Section 50(4) says, "No female shall be searched by anyone excepting a female".

Section 50 is not applicable where the recovery is affected from carry bag, tanker or any other vehicle as it is not a case of personal search. State of Rajasthan v/s Parmanand and another - In this case, the apex court held that each accused must be individually informed that he has a legal right to be searched before a nearest gazetted officer or before a nearest Magistrate. A joint communication of the right available under section 50(1) of the NDPS Act to the accused would frustrate the very purport of section 50.

10. Search in Presence of Independent Witnesses:
Before conducting the search of the suspect, it is necessary for the IO to make every possible effort to join an independent witness, if the accused is apprehended from public place as in such case there is no dearth of independent witnesses at the spot. If any person is not willing to join the investigation then he must clearly mention in the ruqa regarding this fact and he must also mention this fact in the police file as well as in his personal diary.

11. Preparation of Search List (Panchanama) and seizure of case property:
After conclusion of the search, a search list is to be prepared. Drugs or things or documents if recovered and also the place of their recovery are invariably to be mentioned in the search list. A copy of the search list is to be handed over to the agent/owner/occupier of the premises. If any personal search is taken during the search of the premises, a separate search list mentioning the goods recovered from person so searched. In case of no recovery, NIL RECOVERY is to be mentioned in the search list.

The search list should bear the signatures of the person, owner/owner's representative witnesses along with their name, addresses, etc. The copy should bear the dated signature of whom it has been served.

Case property must be properly sealed with the standard seal by the IO and the seal used must be handed over to any of the witnesses. While taking the case property in his charge, the SHO should counter-seal it with his own seal.

12. Preparation of complaint/endorsement for registration of FIR:
After recovery of the NDPS drug or psychotropic substance, the IO should prepare a complaint/endorsement for registration of FIR, which must include the following points:
i. Raiding party's constitution, departure with/without vehicle, arms and ammunition, route taken, the name of the driver as well as accompanying of the informer.
ii. Numbers of independent public witness requested, their place, their background, i.e. whether they were passer-by, rickshaw pullers, residents, etc., and reasons for not joining.
iii. Time must be noted for important aspects like:
   a) Time of making DD entry
   b) Constitution of raiding party
   c) Time of leaving police station
   d) Time of arrival of spot
   e) Time of briefing to the team
   f) Time of nakabandi
   g) Time of apprehending of suspect
iv. Briefing of staff, position of the informer/staff.
v. Time and direction of arrival of the suspect, whether he was carrying something with him, his turnout, etc.
vi. If anybody is accompanying the suspects, he must also be apprehended and interrogated thoroughly.
vii. If any vehicle is used by the accused, its number, make and colour.
viii. Mandatory compliance of provision u/s 50 NDPS Act.
ix. Complete description of packing/wrappers/marking and the contraband.
x. Checking of contraband through field-testing kit.
xi. Seizure of NDPS drugs, sealing by the IO and counter sealing by the SHO at the place of recovery.

INVESTIGATION PROCEDURES:

1. Recording of Statements:
The next important step that is required to be taken is interrogation/examination of the suspects (accused) and the witnesses. Notice under Section 67 of the NDPS Act may be issued and statements about the identity of the person, address, background, education, occupation, involvement in the drug trade, etc., are to be recorded. This notice should be served under the signature of the concerned person. It must be ensured that the statement that is recorded is written in the language which is understood by the suspects/witnesses. The officer in whose presence the statement is given should also put his signature. If the statement is not written by the person himself, the officer should keep a note that the statement was read out and explained to the person in the language known to him.

2. Disposal of Persons Arrested and Articles Seized:
While arresting a person memo may be served to the person under his dated signature as a token of receipt of the same. The person being arrested should be informed of grounds for such arrest as per Sec. 52(1) of the NDPS Act. Other provisions of Section 52 have also to be complied with regard to arrested persons and seized article.

3. Withdrawal of Sample:
As per the amended provisions, the procedure of sampling is done by the learned Illaqa/Duty Magistrate under section 52A of NDPS Act. In other words, the process of withdrawing of samples has to be in the presence and under the supervision of the Magistrate only and the entire exercise has to be certified by him to be correct. Therefore, it is incumbent upon the SHO to forward the samples immediately to the Ld. MM Court for:
a) For withdrawing representative samples in the presence of the Magistrate and certifying the correctness of the list of samples so drawn.
b) Certifying the correctness of the inventory and
c) Certifying photographs of such drugs or substances taken before the Magistrate as true.

After withdrawing of the samples, the same should be sent to the laboratory within 72 hrs. Sometimes when the sample is sent to FSL, it is returned by the lab by raising some objection which is fatal for the case of prosecution. MHC must make sure that there should be no infirmity when the sample and the docket are sent to the lab.

4. Informing the Superior about Seizure and Arrest:
As per requirement of the Act, the immediate superior officer is to be sent a full report of all the particulars of an arrest. This requirement of law is not to be forgotten. Such report should be given within 48 hours of seizure or arrest in terms 57 of the NDPS Act.

5. PC Remand of accused:
The accused should be taken on PC remand to unearth the entire chain of suppliers, drug dealers involved in drug trafficking.

6. Financial Investigation:
Drug offences, unlike most other offences, are committed only with profit motive. One of the strategies to fight drug trafficking is denying the traffickers the fruits of their trafficking. Chapter VA of the NDPS Act provides for forfeiture of such illegally acquired properties. The property derived from or used in illicit traffic of drugs is liable to forfeiture (Chapter VA of the NDPS Act). The provisions of this chapter are applicable to:
1. Person convicted for an offence punishable with imprisonment of 10 years or more;
2. Person convicted for similar offences outside India;
3. Persons detained under PITNDPS Act;
4. Persons, who are arrested or against whom a warrant of arrest or an authorization of arrest has been issued for commission of an offence punishable with imprisonment of 10 years or more;
5. Persons who are arrested or against whom a warrant or authorization of arrest has been issued for commission of an offence under any other corresponding law of any other country;
6. Persons detained under PITNDPS Act.
7. Relatives of the persons referred to above;
8. Associates of persons referred to above.

7. Forfeiture of Property:
i. Freezing of Property: The officer investigating the case can seize or freeze such property by issuing a freezing order under section 68 F.
ii. Confirmation: A copy of the freezing order should be sent within 48 hours to the Competent Authority who has to confirm the order within 30 days.
iii. Issue of Show Cause Notice: The Competent Authority issues a Show Cause Notice to the person whose property is frozen calling upon him to show why the same should not be forfeited (Section 68 H).
iv. Forfeiture of property: After considering the reply to SCN, if any, received, the Competent Authority issues an order forfeiting the whole or part of the property (Section 68 I).
v. Burden of proof: Whenever any property is to be forfeited under this Chapter, the burden of proving that the property is not illegally acquired rests on the person whose property is to be forfeited.
vi. Fine in lieu of forfeiture: The Competent Authority can impose a fine in lieu of the forfeiture of property.
vii. Management of the forfeited property: The Competent Authority is also the administrator and is responsible to receive and manage all the frozen and forfeited properties.
viii. Appeals: Any appeal against the order of a Competent Authority lies with the Appellate Tribunal for Forfeiture of Property.

========================
{historical_cases_text}
FIR Content:
{pdf_content}

GENERATION RULES:
- DO NOT write generic statements like "Follow proper procedures" or "Maintain chain of custody"
- DO write specific statements like "Ensure the seized ganja bundles (exhibits Muddamal-A and Muddamal-B, 13.100 kg) seized on 19-Sep-2025 at 10:25 hrs are sealed with proper seals and panchnama dated 19-Sep-2025 is signed by all panch witnesses"
- Reference specific names: accused names, witness names, officer names from FIR
- Reference specific dates and times from FIR
- Reference specific locations: railway stations, platforms, addresses from FIR
- Reference specific quantities and exhibit numbers from FIR
- Reference specific legal sections that apply to this case
- USE THE PROVIDED HISTORICAL CASES: When relevant, cite the actual historical cases provided above (e.g., "As seen in Case 1: [case title], each accused must be individually informed...", "Following the precedent in Case 2: [case title], ensure...", "To avoid the pitfalls seen in Case 3: [case title], make sure...")
- For juveniles: mention specific safeguards for the named minor accused, referencing relevant case law if applicable
- For women: mention specific protections if applicable, citing relevant precedents
- For Section 50 compliance: mention specific requirements for this search/seizure, including individual communication to each accused (cite State of Rajasthan v/s Parmanand or similar cases)
- For sampling: mention specific requirements for the substances seized in this case, including Magistrate presence under Section 52A, referencing cases where sampling defects led to acquittals
- For FSL: mention specific dispatch requirements for this case's samples (within 72 hours), citing cases where delayed dispatch or improper handling led to evidence rejection
- For pre-raid procedures: reference specific departure entries, raiding party composition, equipment carried, citing cases where procedural lapses affected prosecution
- For search procedures: reference specific authorization requirements, witness joining, sealing procedures, using case law examples where these were critical
- For FIR preparation: reference specific time notations, witness details, compliance documentation required, citing precedents on FIR admissibility
- For investigation: reference specific statement recording, arrest memo, superior officer reporting (Section 57 - 48 hours), using case examples where these were scrutinized
- For financial investigation: reference forfeiture procedures if applicable to this case, citing relevant precedents

EXAMPLES OF GOOD DOS (case-specific):
✓ "Ensure that the consent for search under Section 50 NDPS Act obtained from Anuj S/o Chintamani Yadav on 19-Sep-2025 is properly documented in writing with his signature, indicating he understood his right to be searched before a Gazetted Officer or Magistrate"
✓ "Verify that the 5 ganja bundles (13.100 kg) seized at Surat Railway Station near Speed Parcel Office gate on 19-Sep-2025 at 10:25 hrs are properly sealed with seal numbers recorded in the panchnama dated 19-Sep-2025, and the seal is handed over to one of the panch witnesses as per procedure"
✓ "Ensure that Anuj (aged 16) is produced before the Juvenile Justice Board within 24 hours of arrest (by 20-Sep-2025, 10:25 hrs) and not kept in ordinary police lock-up, as per JJ Act Section 10"
✓ "Ensure that the departure DD entry made before leaving for Surat Railway Station on 19-Sep-2025 includes details of all raiding team members (ASI Dineshji Parthaji Solanki and others), vehicle number, and all equipment carried including digital weighing machine and Drug Identification Kit"
✓ "Verify that independent witnesses were requested at Surat Railway Station (a public place) and if any person refused to join, this fact is clearly mentioned in the ruqa and police file as per procedure"
✓ "Ensure that representative samples from the 13.100 kg ganja bundles (exhibits Muddamal-A and Muddamal-B) are drawn in the presence of the Magistrate under Section 52A NDPS Act and sent to FSL within 72 hours from seizure date (19-Sep-2025)"
✓ "Ensure that a full report of arrest and seizure particulars is sent to the immediate superior officer within 48 hours of arrest/seizure (by 21-Sep-2025, 10:25 hrs) as per Section 57 NDPS Act"

EXAMPLES OF GOOD DON'TS (case-specific):
✗ "Do not delay in sending samples to FSL" (too generic)
✓ "Do not delay dispatch of representative samples drawn from the 13.100 kg ganja bundles (exhibits Muddamal-A and Muddamal-B) to FSL beyond 72 hours from the date of seizure (19-Sep-2025), as per Section 52A NDPS Act requirements"
✗ "Do not violate Section 50" (too generic)
✓ "Do not proceed with personal search of Anuj S/o Chintamani Yadav without first informing him individually (not jointly with others) of his right under Section 50 NDPS Act to be searched before a Gazetted Officer or Magistrate, and ensure this is documented in writing with his signature"
✓ "Do not allow anyone to leave the premises or make outside calls during the search operation at Surat Railway Station near Speed Parcel Office gate, as this may defeat the purpose of the search"
✓ "Do not forget to make proper departure DD entry before leaving for the raid, mentioning raiding team members (ASI Dineshji Parthaji Solanki and others), vehicle details, and all equipment being carried including digital weighing machine and Drug Identification Kit"
✓ "Do not fail to offer yourself to be searched before the accused and independent witnesses at the time of entry into the premises, as per standard procedure"
✓ "Do not proceed with search without obtaining authorization under Section 41(2) NDPS Act from SHO/ACP Sub-Division, and ensure a copy of grounds of belief is sent to immediate official superior"
✓ "Do not fail to mention in the FIR complaint/endorsement the specific times for: DD entry, raiding party constitution, departure from police station, arrival at spot, briefing time, nakabandi time, and time of apprehending suspect Anuj"
✓ "Do not send samples to FSL without ensuring all infirmities are removed, as returned samples with objections are fatal for prosecution case"

Generate 8-10 specific dos and 8-10 specific donts that are directly tied to THIS case's facts, evidence, accused, witnesses, dates, locations, and legal requirements.

IMPORTANT: Wherever relevant, strengthen your dos/donts by referencing the actual historical cases provided above that illustrate:
- Successful prosecution strategies that should be followed
- Common procedural pitfalls that led to acquittals (to avoid)
- Legal precedents that establish mandatory requirements
- Case law that clarifies procedural compliance standards

Examples of incorporating the provided cases:
- "As seen in Case 1: [case title from above], ensure individual Section 50 notice to each accused..."
- "Following the precedent in Case 2: [case title from above], verify that..."
- "To avoid the acquittal scenario in Case 3: [case title from above], make certain that..."
- "As established in Case 4: [case title from above], it is mandatory to..."

This will make the dos/donts more authoritative and legally grounded."""
    
    # Generate dos and donts with structured output
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def generate_dos_donts():
        return llm_model.with_structured_output(DosAndDonts).invoke(content_for_llm)
    
    dos_and_donts = generate_dos_donts()
    
    logger.info(f"Generated {len(dos_and_donts.dos)} dos and {len(dos_and_donts.donts)} donts")

    # Return updated state
    return {
        "dos": dos_and_donts.dos,
        "donts": dos_and_donts.donts,
    }