describe('Tests cases revolving around notebook gradeable access and submition', () => {
    ['student','ta','instructor'].forEach((user) => {
        beforeEach(() => {
            cy.visit('/');
            cy.login(user);
            cy.visit([['development','gradeable','notebook_filesubmission']]);
        });
        it('Should upload file, submit, and remove file', () => {
            const testfile1 = 'cypress/fixtures/file1.txt';
            const testfile2 = 'cypress/fixtures/file2.txt';
            
            //Verify instructor given buttons doesn't give errors
            if (user === 'instructor'){
                cy.get('#radio-student').click();
                cy.get('#user-id-input').contains('user_id:');
                cy.get('#user-id-input > #user_id').type('a');
                cy.get('#ui-id-1').should('be.visible');
                cy.get('#submission-mode-warning').contains('Warning: Submitting files for a student!');
                cy.get('#radio-normal').click();
            }
            cy.get('#user-id-input').should('not.be.visible');

            cy.get('#multiple_choice_0_1').click();
            cy.get('#multiple_choice_0_0').click();
            cy.get('#multiple_choice_0_3').click();
            cy.get('#mc_0_clear_button').click();
            cy.get('#multiple_choice_0_4').click();
            cy.get('#upload1').selectFile(testfile1,{action: 'drag-drop'});

            cy.get('#content_6 > #CodeMirror-lines').type('cow');

            cy.get('#upload2').selectFile(testfile2,{action: 'drag-drop'});
            
            cy.waitPageChange(() => {
                cy.get('#submit').click();
            });
            cy.get('#submitted-files').contains('problem_2_house/file1.txt');
            cy.get('#submitted-files').contains('problem_4_poetry/file2.txt');

        });
    });
});
