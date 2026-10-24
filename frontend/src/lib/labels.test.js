// npm test: one French label for every technical value.
import test from 'node:test';
import assert from 'node:assert/strict';
import { defectLabel, defectTitle, reportStateLabel, alertTopicLabel, roleLabel, roadClassLabel, riskLabel,
  priorityLabel, factorName, factorPhrase, factorEffect, REPORT_TARGET_STATES, REPORT_STATES, apiErrorMessage } from './labels.js';
import { mainFactor } from './risk.js';
import { hazardLabel } from './constants.js';

test('defect classes in French', () => {
  assert.equal(defectLabel('alligator_crack'), 'faïençage');
  assert.equal(defectLabel('pothole'), 'nid-de-poule');
  assert.equal(defectLabel('longitudinal_crack'), 'fissure longitudinale');
  assert.equal(defectLabel('transverse_crack'), 'fissure transversale');
  assert.equal(defectTitle('pothole'), 'Nid-de-poule');
  assert.equal(defectLabel('new_class'), 'new class'); // unknown: readable, never hidden
  assert.equal(hazardLabel('citizen_report'), 'signalement citoyen');
  assert.equal(hazardLabel(null), 'danger');
});
test('states, alerts, roles, classes, levels', () => {
  assert.equal(reportStateLabel('open'), 'Nouveau');
  assert.equal(reportStateLabel('planned'), 'Intervention planifiée');
  assert.deepEqual(REPORT_TARGET_STATES, ['under_review', 'validated', 'planned', 'resolved', 'rejected']);
  assert.ok(REPORT_TARGET_STATES.every(s => REPORT_STATES[s]));
  assert.equal(alertTopicLabel('driver.reroute.alert'), 'Nouvel itinéraire recommandé');
  assert.equal(alertTopicLabel('driver.route.warning'), 'Danger sur l’itinéraire — aucune alternative sûre');
  assert.equal(roleLabel('bus_driver'), 'Conducteur de bus');
  assert.equal(roadClassLabel('national'), 'Route nationale');
  assert.equal(roadClassLabel(null), '—');
  assert.equal(riskLabel('critical'), 'Critique');
  assert.equal(priorityLabel('P2'), 'P2 · Prioritaire');
});
test('M2 factors as readable phrases with their direction', () => {
  assert.equal(factorName({ feature: 'gov:hist_acc_sum_90' }), 'Accidents dans le gouvernorat (90 derniers jours)');
  assert.equal(factorName({ feature: 'gov:nat_acc_sum_7' }), 'Accidents en Tunisie (7 derniers jours)');
  assert.equal(factorName({ feature: 'm1:road_condition', value: 2 }), 'État de la chaussée observé (M1 · 2 défaut(s))');
  assert.equal(factorPhrase({ feature: 'segment:road_class=national', contribution: 0.96 }), 'Route nationale — augmente le risque');
  assert.equal(factorEffect({ contribution: -0.22 }), 'diminue le risque');
  const segment = { top_factors: [{ feature: 'gov:hist_acc_sum_90', contribution: -0.223 }, { feature: 'segment:road_class=motorway', contribution: 1.383 }, { feature: 'm1:road_condition', contribution: 0.2, value: 1 }] };
  assert.equal(mainFactor(segment), 'Autoroute — augmente le risque');
  assert.equal(mainFactor({ top_factors: '[]' }), '—');
});

test('known API errors in French, others unchanged', () => {
  assert.equal(apiErrorMessage('Invalid username or password'), 'Identifiant ou mot de passe incorrect.');
  assert.equal(apiErrorMessage('Username already exists'), 'Cet identifiant est déjà utilisé.');
  assert.equal(apiErrorMessage('Request failed (502)'), 'La requête a échoué (erreur 502).');
  assert.equal(apiErrorMessage('Failed to fetch'), 'Serveur injoignable. Vérifiez la connexion et réessayez.');
  assert.equal(apiErrorMessage('Destination hors de la zone couverte (gouvernorat de Bizerte)'), 'Destination hors de la zone couverte (gouvernorat de Bizerte)');
  assert.equal(apiErrorMessage(''), 'Une erreur est survenue.');
});
