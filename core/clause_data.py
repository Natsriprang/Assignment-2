from core.clauses import Clause, Item


def build_library():
    clauses = [
        Clause("construction_terms", "Construction and Installation Service Agreement",
               plain_paragraphs=[
                   "The Owner agrees to engage the Contractor to build and install the System "
                   "with the installed capacity of [*] kWp (\u201cWorks\u201d) at [*] in "
                   "accordance with the terms and conditions set out in this Agreement.",
                   "The Contractor agrees to supply the Owner with the employee, equipment and "
                   "construction material in good quality in order to complete the works in this "
                   "Agreement.",
               ], category="general"),

        Clause("attachments", "Attachment of this Agreement",
               plain_paragraphs=[
                   "The following attachments shall be considered an integral part of this "
                   "Agreement: (1) Drawings and specifications; (2) Bill of quantities, prices of "
                   "materials and equipment, and labour (BOQ); (3) Quotation; (4) Scope of work; "
                   "(5) Project Schedule; (6) Term of Reference (TOR).",
                   "In the event of any discrepancy between the provisions of this Agreement and "
                   "Attachment, the provisions of this Agreement shall prevail.",
               ], category="general"),

        Clause("price_payment", "Contract Price and Terms of Payment",
               tables=[{
                   "headers": ["Installment", "%", "Amount (THB)", "Condition / Payment Due"],
                   "rows": [
                       ["[*]", "[*]", "[*]", "Payable upon the Owner's confirmation of engagement, "
                        "with the purchase order attached."],
                       ["[*]", "[*]", "[*]", "Payable upon completion of installation of the "
                        "mounting system."],
                       ["[*]", "[*]", "[*]", "Payable upon completion of installation of the PV "
                        "modules."],
                       ["[*]", "[*]", "[*]", "Payable upon completion of installation of the "
                        "inverter."],
                       ["[*]", "[*]", "[*]", "Payable upon completion of installation of the "
                        "electrical system."],
                   ],
               }],
               items=[
            Item("The Owner agrees to pay the Contractor the Contract Price at the fixed total "
                 "amount of THB [*] ([*]), inclusive / exclusive of VAT, the terms of payment "
                 "shall be divided into the installments set out in the payment table."),
            Item("For the purpose of the payment for each installment, the Contractor shall "
                 "provide the Owner with the relevant invoices, and the supporting documents."),
            Item("For the purpose of the payment for each installment, the Owner shall obtain the "
                 "payment documents as specified in clause 3.2 above, and the Owner agrees to "
                 "proceed with the payment to the Contractor within [*] ([*]) working days.",
                 refs=[2]),
            Item("In case the Contractor fails to provide the documents in accordance with "
                 "clause 3.2, the Owner shall reserve the right to reject the relevant payment of "
                 "such installment until the Contractor has collected the payment documents.",
                 refs=[2]),
            Item("In the event that there is any change in the Works under this Agreement which "
                 "affects the Contract Price, the Parties agree to adjust the Contract Price to "
                 "reflect the actual value of the relevant payment."),
        ], category="payment",
           table_headers=["Installment", "%", "Amount (THB)", "Condition / Payment Due"],
           table_rows=[
               ("[*]", "[*]", "[*]", "Payable upon the Owner's confirmation of engagement, with "
                                     "the purchase order attached."),
               ("[*]", "[*]", "[*]", "Payable upon completion of installation of the mounting "
                                     "system."),
               ("[*]", "[*]", "[*]", "Payable upon completion of installation of the PV "
                                     "modules."),
               ("[*]", "[*]", "[*]", "Payable upon completion of installation of the inverter."),
               ("[*]", "[*]", "[*]", "Payable upon completion of installation of the electrical "
                                     "system."),
           ]),

        Clause("contractor_representations", "Contractor\u2019s Representations and Warranties", items=[
            Item("The Contractor warrants that in the performance of this Agreement, the "
                 "Contractor shall provide the appropriate and capable personnel in accordance "
                 "with labor protection laws or other relevant laws."),
            Item("In the event that the personnel of the Contractor having inappropriate "
                 "behavior or working ineffectively according to the assessment of the Owner or "
                 "absence without reasonable cause, the Owner shall have a right to request to "
                 "replace such personnel by notifying in writing to the Contractor, provided that "
                 "the Contractor shall replace the personnel within 15 (fifteen) days from the "
                 "date of receipt of such notification."),
            Item("In the event that the Contractor has transferred its right or obligation to "
                 "any third party, the Contractor shall not be released from any of its "
                 "obligations and undertakings under this Agreement."),
            Item("In the event that the Contractor, the third party and/or the subordinates of "
                 "the Contractor shall perform their duties under this Agreement, the Contractor "
                 "agrees to comply with the rules, regulations, orders that the Owner announces "
                 "in that establishment."),
            Item("The Contractor warrants that the performance of this Agreement shall comply "
                 "with the laws on safety, health and environment, and shall not cause any "
                 "unreasonable annoyance to the Owner."),
        ], category="representations"),

        Clause("owner_representations", "Owner\u2019s Representations and Warranties (Optional)",
               items=[
                   Item("The Owner represents and warrants that it is the lawful owner of, or "
                        "otherwise holds valid rights of possession or use over, the land, "
                        "building and rooftop on which the System is to be installed, and has "
                        "full legal authority to grant the Contractor access to and use of the "
                        "Project site for the purposes of this Agreement."),
                   Item("The Owner represents and warrants that any drawings, structural "
                        "information, specifications or other documents provided by the Owner to "
                        "the Contractor for the purposes of this Agreement are true, accurate and "
                        "complete in all material respects, and the Owner shall promptly notify "
                        "the Contractor in writing of any error or omission in such documents "
                        "that becomes known to the Owner."),
                   Item("The Owner represents and warrants that its engagement of the Contractor "
                        "and the installation of the System at the Project site do not and will "
                        "not conflict with, or cause the Owner to breach, any other agreement, "
                        "lease, mortgage, permit or legal obligation to which the Owner is a "
                        "party or by which the Owner or the Project site is bound."),
                   Item("The Owner shall be responsible for obtaining, at its own cost, any "
                        "licence, permit, or consent of a third party required to lawfully permit "
                        "the installation of the System at the Project site, except to the extent "
                        "such licence, permit or consent falls within the Contractor\u2019s "
                        "obligations under Attachment 6 (Term of Reference)."),
               ], optional=True, included=False, category="representations"),

        Clause("taxation", "Taxation of the Government Fees", items=[
            Item("The Contractor shall be solely responsible for the payment of its income "
                 "taxes, government fees and relevant duties under this Agreement."),
            Item("The Contractor shall deduct the withholding taxes from each due and payable "
                 "amount according to the revenue code (excluding value-added tax) according to "
                 "the laws, regulations, announcements, rules of the Ministry of Finance, orders "
                 "of the Director-General of the Revenue Department including the other laws "
                 "enforced in such period and in the future."),
        ], category="general"),

        Clause("completion_deadline", "Completion Deadline", items=[
            Item("The Owner agrees that the Contractor shall commence the Works under this "
                 "Agreement within [*] and the Contractor agrees to complete the Works within [*] "
                 "or within 150 days from the signing date of this Agreement."),
            Item("Unless otherwise agreed by the Parties, if the Contractor fails to complete "
                 "the Works within the stipulated deadline as specified in clause 6.1, the Owner "
                 "has the right to claim liquidated damages from the Contractor at the rate of "
                 "0.05 (zero point zero five) percent of the Contract Price per day"
                 "⟦ld_cap| but not more than {pct} of the Contract Price⟧.", refs=[1]),
        ], category="schedule"),

        Clause("personnel_responsibility", "Responsibility to the Personnel of the Contractor", items=[
            Item("The Contractor shall control the personnel of the Contractor to comply with "
                 "the rules and regulations of the Owner which are currently in effect or which "
                 "may be in effect in the future. The Contractor agrees to appoint a "
                 "\u201cCoordinator\u201d of the Contractor to be responsible for the execution of "
                 "this Agreement."),
            Item("The Contractor shall be responsible for all damage caused by the "
                 "Contractor\u2019s personnel, whether in regard to negotiorum gestio or "
                 "negligence, which causes the Owner damage to the Contractor and the Project."),
            Item("In the event that the Owner has provided insurance policies, for instance, "
                 "fire insurance, accident insurance, third party liability insurance or any "
                 "insurance related to the business of the Owner, for which those insurance "
                 "policies shall cover losses arising from any fault of the Contractor or its "
                 "personnel, provided that the Contractor shall be responsible for the first "
                 "deductible as specified in those policies, including any other losses not "
                 "covered under those policies."),
        ], category="personnel"),

        Clause("confidentiality", "Confidentiality Agreement and Use of Information", items=[
            Item("The Contractor shall preserve the interests of the Owner and shall not "
                 "collaborate, assist or give advice to any third party which might cause any "
                 "damage to the Owner or compete with the business of the Owner, directly or "
                 "indirectly and in any means."),
            Item("Unless otherwise agreed in writing by the other Party, the receiving Party "
                 "shall keep the details of this Agreement confidential and shall not disclose it "
                 "to any third party, except in the following cases:",
                 lettered=[
                     "(1) Disclosure by either Party to the extent necessary for the performance "
                     "of a duty or exercise of legal rights arising from this Agreement",
                     "(2) Disclosure by either Party to the group or affiliates of that Party to "
                     "the extent necessary for the performance of this Agreement",
                     "(3) Disclosure by either Party who is required to do so by law, regulation "
                     "or rule of the Stock Exchange or any other authority, including that "
                     "Party\u2019s insurer, auditor, or consultant.",
                     "(4) Disclosure by either Party to a competent court having jurisdiction in "
                     "connection with the applicable law.",
                 ]),
            Item("The Parties have an obligation not to disclose any information specified in "
                 "clause 8.2 above, however this shall not apply to the following information:",
                 refs=[2], lettered=[
                     "(1) Information that is publicly known and not due to a breach of any "
                     "confidentiality agreement of the Parties;",
                     "(2) Confidential information which was already in the possession of the "
                     "receiving Party; or",
                     "(3) Information that a Party receives from a third party without breach of "
                     "the Parties\u2019 confidentiality agreements.",
                 ]),
            Item("The Contractor has fully understood that the Contractor is able to access any "
                 "Confidential Information in any form, for instance, design, detail, "
                 "specification, plan, information technology, material, copy, photograph, map, "
                 "geographic design, computer software, drawing, formula, or other innovation "
                 "arising from the business of the Owner, and any other information which the "
                 "Contractor becomes aware of after the execution of this Agreement."),
            Item("For the purpose of clause 8.2 above, the Parties fully understand and agree "
                 "that the foregoing means \u201cConfidential Information\u201d, which is an "
                 "essential term of this Agreement.", refs=[2]),
            Item("The Contractor shall keep the Confidential Information confidential and shall "
                 "use it only for communication, consultation, discussion and coordination "
                 "between the persons designated by the Owner and for the performance of this "
                 "Agreement by the Contractor."),
            Item("The Parties agree that the Contractor\u2019s confidentiality obligations under "
                 "this Agreement shall survive the termination or expiration of this Agreement. "
                 "If the Contractor breaches the confidentiality obligation during the Works, the "
                 "Contractor agrees that the Owner has the right to terminate this Agreement as "
                 "well as to withhold any outstanding amount of the Contract Price due at the "
                 "time of the breach, and any subsequent amount of the Contract Price (if any)."),
        ], category="confidentiality"),

        Clause("suspension", "Suspension of Works", items=[
            Item("At any time, the Owner may request the Contractor to suspend any part of the "
                 "Works under this Agreement in part or in whole, in case of force majeure, "
                 "emergency or necessity of the Owner which prevents the Contractor from "
                 "performing the affected part of the Works during the relevant period of time."),
            Item("In the event that the suspension arises from the necessity of the Owner, the "
                 "Owner agrees to extend the reasonable period of time for the Works and the "
                 "Contractor may claim any expenses incurred from the Owner."),
            Item("In the event that the suspension arises from the Contractor, the Contractor "
                 "may request to extend the reasonable period of time for the Works under this "
                 "Agreement and the Owner may claim any expenses incurred from the Contractor."),
        ], category="suspension"),

        Clause("inspection", "Inspection of Works",
               plain_paragraphs=[
                   "The Owner, or its advisor or representative, has the right to inspect the "
                   "performance of obligations by the Contractor\u2019s Coordinator at any time "
                   "and reserves the right to give advice or to inform the Coordinator to perform "
                   "the obligations under this Agreement strictly, or to notify the Contractor in "
                   "case of requesting a change of personnel or the Coordinator.",
               ], category="general"),

        Clause("drawing_discrepancy", "Discrepancy in Work Drawings", items=[
            Item("The Contractor warrants that it has thoroughly reviewed and understood the "
                 "drawings and specifications. If any error arising from engineering or technical "
                 "principles, or any defect in the Contractor\u2019s documents, is found, the "
                 "Contractor shall rectify such documents, including any Works already performed, "
                 "at the Contractor\u2019s own expense, unless such error or defect arises from a "
                 "material change to the construction site made by the owner of the site itself."),
            Item("In the event of any material change to the construction site that affects the "
                 "Contractor\u2019s performance of the Works under this Agreement, the Parties "
                 "agree to extend the period for the Works by a period equal to that required to "
                 "revise the design and/or construction to make it appropriate and sufficiently "
                 "safe, provided that the Contractor may charge the cost of such revision in "
                 "addition to the Contract Price."),
        ], category="construction_quality"),

        Clause("termination", "Breach and Termination", items=[
            Item("If either Party fails to perform its obligations under this Agreement, the "
                 "other Party may give written notice requiring that Party to perform its "
                 "obligations and remedy such failure within a reasonable period, being not less "
                 "than 45 (forty-five) days. If such Party performs its obligations and remedies "
                 "the failure within such period, the failure shall not be deemed an event of "
                 "default."),
            Item("The Owner shall have the right to terminate this Agreement by written notice "
                 "specifying the date on which the Agreement shall terminate, delivered to the "
                 "Contractor not less than 30 (thirty) days before such termination date, if the "
                 "Contractor:", lettered=[
                     "(a) becomes bankrupt, enters into liquidation, or is subject to an absolute "
                     "receivership order;",
                     "(b) fails to comply with the notice under clause 12.1 of this Agreement;",
                     "(c) abandons the Works or clearly indicates an intention no longer to "
                     "perform its obligations under this Agreement, or fails to complete the "
                     "Works by the stipulated deadline without reasonable cause.",
                 ], refs=[1]),
            Item("The Contractor shall have the right to terminate this Agreement by written "
                 "notice specifying the date on which the Agreement shall terminate, delivered to "
                 "the Owner not less than 30 (thirty) days before such termination date, if:",
                 lettered=[
                     "(a) the Owner becomes bankrupt, enters into liquidation, or is subject to "
                     "an absolute receivership order;",
                     "(b) the Contractor does not receive payment due to it within 30 (thirty) "
                     "days after notice is given under clause 12.1 of this Agreement;",
                     "(c) the Works are suspended for a continuous period exceeding 60 (sixty) "
                     "days, through no fault of the Contractor and not due to force majeure, and "
                     "such suspension affects the Works as a whole, in which case the Contractor "
                     "shall remain entitled to claim damages from the Owner.",
                 ], refs=[1]),
            Item("The Parties may agree to terminate this Agreement by mutual written "
                 "agreement."),
            Item("Once either Party exercises its right to terminate this Agreement, the "
                 "Parties shall negotiate to agree or determine the value of the Works completed, "
                 "as well as any other amounts outstanding under this Agreement."),
            Item("The Owner may withhold any amount payable to the Contractor until the value of "
                 "the drawings, the Works performed, and any other expenses incurred by the Owner "
                 "have been determined."),
            Item("Neither Party shall be deemed in breach of this Agreement where it is unable "
                 "to perform due to force majeure."),
            Item("In any case where the Contractor breaches this Agreement or causes damage to "
                 "the Owner, the Contractor agrees that the Owner may deduct the amount of such "
                 "damages or expenses from the performance bond (contract security) or from the "
                 "remaining Contract Price"
                 "⟦damages_cap|, provided that the total damages shall not exceed {pct_sym} "
                 "of the Contract Price⟧, within 15 (fifteen) days of the "
                 "Owner\u2019s written notice to the Contractor."),
        ], category="termination"),

        Clause("force_majeure", "Force Majeure", items=[
            Item("Subject to the limitations set forth in this Agreement, in the event that a "
                 "force majeure event affects either Party and causes such Party to be unable to "
                 "perform such affected obligation, in whole or in part, the affected Party shall "
                 "inform the non-affected Party of the force majeure event as soon as "
                 "practicable."),
            Item("In this Agreement, \u201cForce Majeure\u201d means any event, condition or "
                 "circumstance beyond the reasonable control of the affected Party, without the "
                 "fault or negligence of the Party claiming the force majeure event, including:",
                 lettered=[
                     "1) lightning, storms, floods or unusually severe weather conditions; or",
                     "2) earthquake, landslide or other unforeseeable natural disaster; or",
                     "3) protests and/or other strikes or labor disputes; or",
                     "4) war, invasion, terrorist actions, embargo, riot or civil unrest; or",
                     "5) land expropriation or government intervention; or",
                     "6) any change in law or government action; or",
                     "7) epidemic.",
                 ]),
            Item("In case of a Force Majeure event, the affected Party shall notify the other "
                 "Party in writing immediately and use reasonable efforts to remedy the event."),
            Item("If force majeure continues for 180 (one hundred and eighty) consecutive days "
                 "and for more than 365 (three hundred and sixty-five) days in total, either "
                 "Party has the right to terminate this Agreement without default."),
        ], category="force_majeure"),

        Clause("notice", "Notice",
               tables=[{
                   "headers": ["Party", "Item", "Details"],
                   "rows": [
                       ["Owner", "Company name", "[*]"], ["", "Attention", "[*]"], ["", "Address", "[*]"],
                       ["", "Phone", "[*]"], ["", "Email", "[*]"],
                       ["Contractor", "Company name", "[*]"], ["", "Attention", "[*]"], ["", "Address", "[*]"],
                       ["", "Phone", "[*]"], ["", "Email", "[*]"],
                   ],
               }],
               plain_paragraphs=[
                   "For the purpose of the performance of this Agreement being effective and "
                   "correct, the Parties have designated the addressee and address for "
                   "communication and notification as set out in the notice table.",
                   "Any communication with the addressee shall be considered a notification to "
                   "the receiving Party. Any change in the address or addressee shall be made in "
                   "writing and shall be used in subsequent communications.",
               ], category="general"),

        Clause("miscellaneous", "Miscellaneous", items=[
            Item("If one or more provisions of this Agreement become invalid, void or voidable "
                 "for any reason, such invalidity shall not affect the other remaining "
                 "provisions."),
            Item("The Parties agree that if a Party wishes to amend any provision(s), it shall "
                 "be made in writing and signed by both Parties."),
            Item("Any waiver or extension of a period of time to perform obligations under this "
                 "Agreement shall be made in writing."),
            Item("In the event any dispute arises out of or in connection with this Agreement, "
                 "the Parties shall seek an amicable resolution through formal negotiations "
                 "between senior officials of both Parties."),
            Item("This Agreement shall be governed by and interpreted in accordance with the "
                 "laws of Thailand."),
        ], category="general"),
    ]

    position = 0
    for c in clauses:
        if c.included:
            position += 1
            c.authored_number = str(position)
    return clauses