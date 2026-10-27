# Draft Contract

The app helps in-house legal draft a rooftop solar construction and installation contract under Thai law. The user can upload an Excel term sheet or fill the field and the app turns it into a Word contract. The app also lets the user ask for changes, checks the result, and produces an approval memo.

App URL: https://assignment-2-zh2ehad4ba2khekqdsyscr.streamlit.app/

## How to use the app

1. Open the URL and type the password.
2. Type an OpenAI API key and press Update API Key on the side bar.
3. Go to Draft contract. Upload a term sheet (the Excel file). The template is data/term_sheet_template_EN.xlsx. Three Excel examples are in test_cases/.
4. **Term sheet page**: In this page, user can choose to upload the Excel term sheet or fill in the term manually. User can make changes to various terms and conditions. User can add a request directly in the Additional condition block, which will transfer the input to the next page. 
When the Excel file is uploaded, user can press Auto-fill the form and press Continue at the bottom of the page. The app then reads the sheet and shows problems such as missing items, conflicts information with the term sheet conditions or requirements.
5. **Clauses page**: User can ask a question about the contract, add optional clauses, and ask for a new clause. The chatbot will provide the proposed change and the change will be made to the contract only after the user pressed Apply. You can also reject, edit, or undo the applied request. User can also use preview clause function to see the content of each clause. Any changes made will also be translate into this preview clause tab. 
6. **Preview page**: There are 2 tabs in this page. The Contract tab has the summary of the contract, the list of changes and the final draft. The Checks tab has the risks and a review of the contract. The user can download the contract and the approval memo in Word document at the bottom of the page.

## What the code does and what the AI does
The code reads the term sheet, filling in the parties, price, VAT, dates and payment table, numbering the clauses, and checking every quote and figure that the AI gives. Nothing the AI writes goes into the contract unless the user applies it.

## AI steps
The counter on the page shows the number of AI calls in the run. Every run has at least 5 calls.
Step of the AI calls:
1. Check the term sheet for problems. `term_sheet_check`
2. Interpret the request which reads what the user typed and the term sheet, says which clauses change and writes the changed sentence. `interpret`
3. Find references clauses from the reference library for a new clause (only when the user asks for a new clause). `select_references`
4. Generate the content by writing the new clause (only when the user asks for a new clause). `draft_clause`
5. Check the risks arising from the changes. `risk_flagging`
6. Review using two independent reads of the final draft look for sentences that contradict each other. `review_by_matter`, `review_by_changes`
7. Summary and memo. The model writes the overview; code writes the facts table, the list of changes and the approval memo. `exsum_overview`

Shortest run (no changes made to the contract) uses 5 calls including step 1, 2, 6 (this step has 2 AI calls), and 7.

## Files
1. app.py: entry point and password page
2. api_key.py: course credentials module
3. views/: the pages and the three steps
4. ai/: the AI steps
5. core/: the code that works without AI (term sheet, clauses, numbering, Word files, memo)
6. data/term_sheet_template_EN.xlsx: the term sheet template
7. data/reference/: clause library used when drafting a new clause
8. test_cases/: the 3 sample term sheets

## Test cases
3 test cases (the Excel files in test_cases/). 
Case 1 is the shortest run. 
Case 2 uses every step. 
Case 3 shows a limitation.

### Case 1: standard contract with no changes.
File: case1_term_sheet.xlsx
Steps
1. Upload the file, press Auto-fill the form, and press Continue.
2. On the Clauses step, press the analysis button without typing a request, then Continue.
3. Open the Preview step. Open the Contract tab and the Checks tab. Download the Word file and the approval memo.

Expected
- The term sheet is read with the country of registration of both parties are missing, the registration number of owner does not match the requirement in the term sheet.
- The facts table shows a brief summary of the key terms. 
- The draft has the 15 standard clauses and blank fields including the place of signing (if user did not choose) and the Parties' country in the header, and the witnesses in the signature block. The Word file shows them as [*].
- "Changes made to the contract" in the Preview page should say "No change from the standard contract." and the Risk box says there is nothing to assess, with no AI call.
- The overview describes the contract and says nothing has changed from the standard contract. Review also finds no contradiction.
- The memo has the contract title, the project, both parties and the key terms, To and Urgency are blanked, two sign-off boxes for the proposer and Legal Department.

### Case 2: requested changes, optional clauses, a new clause and a question
File: case2_term_sheet.xlsx 

Steps
1. Upload the file, press Auto-fill the form, and press Continue.
2. On the Clauses step, press the analysis button. Look at what the app suggests.
3. Type: Increase the delay damages to 0.5% a day and remove the cap on this damage. Apply the proposal.
4. Select the optional clauses Late-payment interest and Guarantee.
5. Type: Add an advance payment clause: the Owner pays 20% of the Contract Price in advance. The app should answer in one of two ways (see Expected). Follow its question, then apply the drafted clause and place it after the clause on payment.
6. Type a question: What is the cap on total damages deducted?
7. Continue to the Preview step and look at both tabs. Download the Word file and the memo.

Expected
- The Owner's Representations and Warranties clause is suggested by the app because the roof owner is a third party. The user can choose to apply the clause.
- The additional condition for Suspension of Works is a proposed change to that clause.
- The additional condition for Force Majeure is a proposal to take the point "7) epidemic." out of the Force Majeure clause. When applied it should take the point out and the list around it is renumbered.
- The request about the delay damages is one proposal that changes the rate to 0.5% and takes the cap out of the same sentence. After applied, it will be revised into clause 6.2.
- Late-payment interest is added at the end of the clause on payment and the page says where it will be added. Guarantee is a new clause added after Taxation clause automatically.
- The reply to the advance payment request can go two ways. First, it asks whether to look for references and draft a new clause. Second, it asks whether the user means an existing clause. Both ways require the user to confirm and the clause is then drafted.
- The advance payment clause is drafted from the reference library and the references used are listed under it.
- The question is answered from the draft and the answer lists what the agent looked at but the draft does not change.
- The facts table shows the key terms and changes.
- The Risk tab shows at least one risk for taking out the cap on liquidated damage. Changes made to the contract will list the rate change and the removed cap, the advance payment clause as new, and the Suspension of Works condition.
- Review tab finds that the delay damages now have no cap while Breach and Termination still has a cap on total damages, and names both sentences.
- Limitation of Review: Review can report a contradiction between two sentences that are about different matters although the prompt tells the model to report only sentences that cannot both be applied. This may require human verification of the findings.

### Case 3: a limitation (law other than the template's, and a clause with no reference)
File: case3_term_sheet.xlsx (University of Melbourne, 100 kWp rooftop in Victoria, Australia; governing law "Victoria, Australia").

Steps
1. Upload the file, press Auto-fill the form, and press Continue.
2. On the Clauses step, type: Add a limitation of liability clause where the Contractor's total liability under this Agreement is limited to the Contract Price.
3. Apply the drafted clause. Continue to the Preview step.
4. Read the Miscellaneous clause, the Taxation clause and the Checks tab.

Expected
- The governing law sentence in Miscellaneous says the Agreement is governed by the laws of Victoria, Australia.
- The contract is still the template use under Thai law wording. The app does not make changes in the contract to the foreign law.
- No clause in the reference library is about limitation of liability. Therefore, the clause is written by the model from general drafting practice and the page says that no reference was found. Its wording is not checked against Australian law.
- The Risk tab may flag the new clause, but it would not say that the clause is wrong for the chosen law.

## Limitations

1. The template is written under Thai law. If uses another governing law, the app does not change the contract and does not warn about possible conflicts (case 3).
2. If no clause in the reference library fits a new clause, the model writes it from general drafting practice. The model may also write more than asked (case 3).
3. The Review step can report two sentences as contradicting even if they are about different matters (case 2).
4. The Preview page: The list "Changes made to the contract" and the Risk step look at changes to the standard wording and at new clauses that the user asked for. They do not look at optional clauses that the user ticks on the Clauses page.
5. The chat agent answers questions about limits from the term sheet values. It can miss a sentence of the draft when the draft uses other words (case 2, question about the cap on total damages). If the draft was changed, the answer may not match the draft.
